import { authMemory } from '../auth/AuthContext';
export const MAX_BYTES = 20 * 1024 * 1024;
export type Metadata = { id: string; document_id: string; institution_id: string; number: number; original_name: string; size: number; mime: string; format: string; sha256: string; created_at: string; state: string; active: boolean; registered: boolean; revision: number };
export type Job = { id: string; version_id: string; state: string };
export class ApiError extends Error { constructor(public status: number, public code = '') { super(errorMessage(status)); } }
export function errorMessage(status: number): string {
  return ({0:'서버에 연결하지 못했습니다. API 주소와 연결 상태를 확인해 주세요.',401:'세션이 없거나 만료되어 자료에 접근할 수 없습니다. 다시 로그인해 주세요.',403:'이 작업을 수행할 권한이 없습니다.',404:'자료 또는 작업을 찾을 수 없습니다. 접근 가능한 자료인지 확인해 주세요.',409:'현재 상태와 요청이 충돌합니다. 상태를 새로고침한 후 확인해 주세요.',422:'요청 값이 올바르지 않습니다.',400:'파일명 또는 공개·합성 자료 확인 값을 확인해 주세요.',413:'파일은 20 MiB 이하여야 합니다.',415:'지원하지 않거나 실제 형식이 올바르지 않은 파일입니다.',500:'서버에서 요청을 처리하지 못했습니다.',503:'저장소 또는 서버를 사용할 수 없습니다. 잠시 후 다시 확인해 주세요.'} as Record<number,string>)[status] ?? '요청을 처리하지 못했습니다. 잠시 후 다시 확인해 주세요.';
}
export async function validateFile(file: File): Promise<string | null> {
  if (!file.size || file.size > MAX_BYTES) return '파일은 비어 있지 않은 20 MiB 이하 파일이어야 합니다.';
  if (file.name.length > 200 || /[/\\:\x00-\x1f]/.test(file.name)) return '사용할 수 없는 파일명입니다.';
  const ext=file.name.split('.').pop()?.toLowerCase();
  if(ext!=='pdf' && ext!=='hwpx')return 'PDF 또는 HWPX 파일만 선택할 수 있습니다.';
  const header=new Uint8Array(await file.slice(0,8).arrayBuffer());
  if(ext==='pdf' && !new TextDecoder().decode(header).startsWith('%PDF-1.'))return '확장자와 PDF 파일 형식이 일치하지 않습니다.';
  if(ext==='hwpx' && !(header[0]===80 && header[1]===75 && header[2]===3 && header[3]===4))return '확장자와 HWPX 패키지 형식이 일치하지 않습니다.';
  return null; // Full PDF/ZIP/XML validation is authoritative on the server.
}
function validMetadata(v:Metadata){return v && ['id','document_id','original_name','format','mime','sha256','created_at','state'].every(k=>typeof (v as unknown as Record<string,unknown>)[k]==='string') && Number.isFinite(v.size)&&Number.isInteger(v.number)&&typeof v.active==='boolean'&&typeof v.registered==='boolean';}
export function createDocumentsClient(base = import.meta.env.VITE_API_BASE_URL || '/api', transport: typeof fetch = fetch) {
  const root=base.replace(/\/$/,'');
  const version=(d:string,v:string)=>`/documents/${encodeURIComponent(d)}/versions/${encodeURIComponent(v)}`;
  async function request<T>(path:string, init:RequestInit={}):Promise<T>{
    let response:Response;
    try{response=await transport(root+path,{...init,headers:{...init.headers,...(init.method&&init.method!=='GET'&&authMemory.csrf?{'X-CSRF-Token':authMemory.csrf}:{})},credentials:'same-origin',cache:'no-store',redirect:'error'});}catch{throw new ApiError(0);}
    if(!response.ok){if(response.status===401&&typeof window!=='undefined')window.dispatchEvent(new Event('seomuitda-session-expired'));throw new ApiError(response.status);}
    try { return await response.json() as T; } catch { throw new ApiError(500,'invalid_response'); }
  }
  return {
    async list(signal?:AbortSignal){const data=await request<Metadata[]>('/documents?active_only=false',{signal});if(!Array.isArray(data)||data.some(v=>!validMetadata(v)))throw new ApiError(500,'invalid_response');return data;},
    async detail(d:string,v:string){const data=await request<Metadata>(version(d,v));if(!validMetadata(data)||data.document_id!==d||data.id!==v)throw new ApiError(500,'invalid_response');return data;},
    upload:(file:File,classification:'public'|'synthetic',documentId?:string)=>request<{document:Metadata;duplicate:boolean}>(`${documentId?`/documents/${encodeURIComponent(documentId)}/versions`:'/documents'}?filename=${encodeURIComponent(file.name)}`,{method:'POST',headers:{'Content-Type':file.name.toLowerCase().endsWith('.pdf')?'application/pdf':'application/hwp+zip','X-Data-Classification':classification},body:file}),
    parsing:(d:string,v:string)=>request<Job>(version(d,v)+'/parsing'),
    retryParsing:(d:string,v:string)=>request<Job>(version(d,v)+'/parsing/retry',{method:'POST'}),
    enqueueChunks:(d:string,v:string)=>request<Job>(version(d,v)+'/chunk-jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}),
    chunkStatus:(d:string,v:string,j:string)=>request<Job>(version(d,v)+'/chunk-jobs/'+encodeURIComponent(j)),
    retryChunks:(d:string,v:string,j:string)=>request<Job>(version(d,v)+'/chunk-jobs/'+encodeURIComponent(j)+'/retry',{method:'POST'}),
    deregister:(d:string)=>request<{document_id:string;registered:boolean}>('/documents/'+encodeURIComponent(d),{method:'DELETE'}),
    async original(d:string,v:string):Promise<Blob>{let response:Response;try{response=await transport(root+version(d,v)+'/original',{credentials:'same-origin',cache:'no-store',redirect:'error'});}catch{throw new ApiError(0);}if(!response.ok){if(response.status===401&&typeof window!=='undefined')window.dispatchEvent(new Event('seomuitda-session-expired'));throw new ApiError(response.status);}return response.blob();},
  };
}
export const documentsClient=createDocumentsClient();
