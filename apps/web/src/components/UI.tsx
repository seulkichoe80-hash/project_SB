import type { ButtonHTMLAttributes, ReactNode } from 'react';

export function StatusBadge({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'info' | 'warning' | 'error' }) {
  return <span className={`status-badge status-badge--${tone}`}><span className="status-dot" aria-hidden="true" />{children}</span>;
}

export function Button({ variant = 'primary', className = '', ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' }) {
  return <button className={`button button--${variant} ${className}`} type="button" {...props} />;
}

export function PageTitle({ eyebrow, title, description, actions }: { eyebrow: string; title: string; description: string; actions?: ReactNode }) {
  return <div className="page-title"><div><p className="eyebrow">{eyebrow}</p><h1 tabIndex={-1} id="page-heading">{title}</h1><p className="page-description">{description}</p></div>{actions && <div className="page-actions">{actions}</div>}</div>;
}

export function LoadingState({ message = '화면을 불러오고 있습니다.' }: { message?: string }) {
  return <div className="state-message" role="status" aria-live="polite"><span className="loading-ring" aria-hidden="true" /><p>{message}</p></div>;
}

export function EmptyState({ title, description, icon = 'document' }: { title: string; description: string; icon?: 'document' | 'spark' }) {
  return <div className="state-message"><span className="state-icon"><Icon name={icon} /></span><h2>{title}</h2><p>{description}</p></div>;
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return <div className="error-state" role="alert"><h2>화면을 불러오지 못했습니다</h2><p>{message}</p>{onRetry && <Button variant="secondary" onClick={onRetry}>다시 시도</Button>}</div>;
}

export type IconName = 'home' | 'document' | 'spark' | 'help' | 'arrow' | 'shield' | 'check';
export function Icon({ name }: { name: IconName }) {
  const paths: Record<IconName, ReactNode> = {
    home: <><path d="m3 10 9-7 9 7" /><path d="M5 9v12h14V9M9 21v-8h6v8" /></>,
    document: <><path d="M6 3h8l4 4v14H6zM14 3v5h4M9 12h6M9 16h6" /></>,
    spark: <><path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5zM20 2v4M18 4h4" /></>,
    help: <><circle cx="12" cy="12" r="9" /><path d="M9.5 9a2.5 2.5 0 1 1 4 2c-1.5 1-1.5 1-1.5 3M12 17h.01" /></>,
    arrow: <path d="M4 12h16m-6-6 6 6-6 6" />,
    shield: <><path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6z" /><path d="m8 12 3 3 5-6" /></>,
    check: <path d="m5 12 4 4L19 6" />,
  };
  return <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">{paths[name]}</svg>;
}
