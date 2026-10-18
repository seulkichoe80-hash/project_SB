"""All new provider tests use scripted, synthetic in-memory transport, never external HTTP."""
import concurrent.futures
import copy
import hashlib
import json
import logging
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from pydantic import ValidationError
from apps.api.errors import DomainError
from apps.api.models import Principal
from apps.api.provider_budget import (SimulationBudgetLedger, Reservation, BudgetClaim)
from apps.api.provider_safety import (ProviderSettings, ProviderSafetyGateway, FakeTransport, FakeResponse,
    BlockedTransport, encoded, approved_simulation_input, ApprovedSimulationInput, SimulationRequest)
from apps.api.provider_fake_adapters import (FakeWorkflowExtractionAdapter, FakeLLMAdapter, FakeEmbeddingAdapter,
    SimulationDocumentPermission, SimulationEmbeddingPermission)


A=Principal('synthetic-manager','A','manager')
B=Principal('synthetic-manager-B','B','manager')
WORKER=Principal('synthetic-worker','A','worker')
READER=Principal('synthetic-reader','A','reader')
H=lambda text:hashlib.sha256(text.encode()).hexdigest()


def complete(output=None, **changes):
    data={'status':'complete','model':'fake-model-v1','output':{} if output is None else output,
          'usage':{'input_tokens':5,'output_tokens':2}}
    data.update(changes)
    return FakeResponse(body=encoded(data))


def error(status, *, known=True):
    return FakeResponse(status=status,body=encoded({'usage':{'input_tokens':0,'output_tokens':0}} if known else {'error':'SYNTHETIC_PRIVATE_MARKER'}))


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'costs.sqlite3'
        self.now=1000.0;self.ledger=SimulationBudgetLedger(self.path,clock=lambda:self.now,ttl=2)
        self.ledger.provision(A,1000);self.ledger.open_job(A,'job',1000)
        self.r=Reservation(10,10,1_000_000,1_000_000,2,100)
    def tearDown(self):self.tmp.cleanup()
    def reserve(self,key='request',principal=A,job='job',reservation=None):
        return self.ledger.reserve(principal,job,key,H(key),reservation or self.r)
    def settled(self,key='request',usage=(3,2)):
        claim=self.reserve(key);n=self.ledger.start(A,claim)
        self.ledger.record(A,claim,n,*usage,H('receipt'));self.ledger.finish(A,claim,'completed');return claim
    def assert_account(self,held,spent):
        balance=self.ledger.balance(A);self.assertEqual((balance['held'],balance['spent']),(held,spent))
        self.assertEqual(balance['actual_spent'],0);self.assertEqual(balance['currency'],'SIMULATED_USD')
        events=self.ledger.events(A);self.assertEqual(sum(x['delta_held'] for x in events),held)
        self.assertEqual(sum(x['delta_spent'] for x in events),spent)
        with self.ledger.transaction() as db:
            for table in ['provider_budget_jobs','provider_budget_requests']:
                row=db.execute(f'SELECT COALESCE(SUM(held),0),COALESCE(SUM(spent),0) FROM {table} WHERE institution=?',('A',)).fetchone()
                self.assertEqual(tuple(row),(held,spent))
    def test_exact_integer_rounding_and_bounds(self):
        r=Reservation(1,1,100_000,500_000);self.assertEqual(r.per_attempt,1)
        for value in [-1,True,1.1,'100']:
            with self.subTest(value=value),self.assertRaises(DomainError):Reservation(value,1,1,1)
    def test_per_request_ceiling_precedes_reservation(self):
        with self.assertRaises(DomainError):Reservation(10,10,1_000_000,1_000_000,2,39)
        self.assert_account(0,0)
    def test_reserve_settle_release_balances(self):
        claim=self.reserve();self.assert_account(40,0);n=self.ledger.start(A,claim)
        self.ledger.record(A,claim,n,3,2,H('receipt'));self.assert_account(20,5)
        self.ledger.finish(A,claim,'completed');self.assert_account(0,5)
    def test_duplicate_reservation_has_no_second_owner(self):
        self.assertIsNotNone(self.reserve());self.assertIsNone(self.reserve());self.assert_account(40,0)
    def test_changed_fingerprint_or_job_is_conflict(self):
        self.reserve()
        with self.assertRaises(DomainError):self.ledger.reserve(A,'job','request',H('different'),self.r)
        self.ledger.open_job(A,'another',1000)
        with self.assertRaises(DomainError):self.ledger.reserve(A,'another','request',H('request'),self.r)
        self.assert_account(40,0)
    def test_changed_rate_policy_duplicate_rejected(self):
        self.reserve()
        with self.assertRaises(DomainError):self.reserve(reservation=Reservation(10,10,1_000_001,1_000_000,2,100))
        self.assert_account(40,0)
    def test_settlement_and_finish_are_idempotent(self):
        claim=self.settled();self.ledger.record(A,claim,1,3,2,H('receipt'))
        self.ledger.finish(A,claim,'completed');self.assert_account(0,5)
    def test_conflicting_settlement_does_not_recharge(self):
        claim=self.settled()
        with self.assertRaises(DomainError):self.ledger.record(A,claim,1,4,2,H('other'))
        self.assert_account(0,5)
    def test_pre_send_cancel_releases_all(self):
        self.reserve();self.ledger.cancel(A,'request');self.ledger.cancel(A,'request');self.assert_account(0,0)
        with self.assertRaises(DomainError):self.ledger.start(A,BudgetClaim('request','wrong'))
    def test_cancel_after_send_retains_only_uncertain_attempt(self):
        claim=self.reserve();self.ledger.start(A,claim);self.ledger.cancel(A,'request')
        self.assertEqual(self.ledger.request(A,'request')['state'],'uncertain');self.assert_account(20,0)
        self.ledger.cancel(A,'request');self.assert_account(20,0)
    def test_reconcile_known_usage_and_repeated_receipt(self):
        claim=self.reserve();self.ledger.start(A,claim);self.ledger.unknown(A,claim)
        self.ledger.reconcile(A,'request',4,2,H('verified'));self.ledger.reconcile(A,'request',4,2,H('verified'))
        self.assert_account(0,6)
        with self.assertRaises(DomainError):self.ledger.reconcile(A,'request',4,3,H('changed'))
    def test_worker_cannot_authorize_reconciliation(self):
        claim=self.reserve();self.ledger.start(A,claim);self.ledger.unknown(A,claim)
        with self.assertRaises(DomainError):self.ledger.reconcile(WORKER,'request',0,0,H('r'))
        self.assert_account(20,0)
    def test_missing_usage_is_not_refunded_on_reopen(self):
        claim=self.reserve();self.ledger.start(A,claim);self.ledger.unknown(A,claim)
        self.ledger=SimulationBudgetLedger(self.path,clock=lambda:self.now,ttl=2)
        self.assert_account(20,0);self.assertIsNone(self.reserve())
    def test_expired_inflight_recovers_as_uncertain(self):
        claim=self.reserve();self.ledger.start(A,claim);self.now+=3
        self.assertEqual(self.ledger.recover(A),1);self.assert_account(20,0)
        with self.assertRaises(DomainError):self.ledger.record(A,claim,1,0,0,H('late'))
    def test_expired_unsent_reservation_is_released(self):
        self.reserve();self.now+=3;self.assertEqual(self.ledger.recover(A),1);self.assert_account(0,0)
    def test_cancel_between_retries_keeps_known_spend(self):
        claim=self.reserve();n=self.ledger.start(A,claim);self.ledger.record(A,claim,n,3,2,H('r'))
        self.ledger.cancel(A,'request');self.assert_account(0,5)
    def test_cancel_job_blocks_new_requests_and_preserves_unknown(self):
        a=self.reserve('a');self.reserve('b');self.ledger.start(A,a);self.ledger.cancel_job(A,'job')
        self.assert_account(20,0)
        with self.assertRaises(DomainError):self.reserve('c')
    def test_retry_attempt_count_does_not_multiply(self):
        claim=self.reserve()
        for n in [1,2]:
            self.assertEqual(self.ledger.start(A,claim),n);self.ledger.record(A,claim,n,0,0,H(str(n)))
        with self.assertRaises(DomainError):self.ledger.start(A,claim)
        self.ledger.finish(A,claim,'failed');self.assert_account(0,0)
    def test_usage_over_reservation_cannot_create_untracked_spend(self):
        claim=self.reserve();n=self.ledger.start(A,claim)
        with self.assertRaises(DomainError):self.ledger.record(A,claim,n,11,0,H('r'))
        self.ledger.unknown(A,claim);self.assert_account(20,0)
    def test_account_and_job_limits(self):
        self.ledger.open_job(A,'small',39)
        with self.assertRaises(DomainError):self.reserve(job='small')
        self.ledger.open_job(A,'large',1000)
        for i in range(25):self.reserve('r'+str(i),job='large')
        with self.assertRaises(DomainError):self.reserve('over')
        self.assert_account(1000,0)
    def test_cross_institution_read_cancel_settle_not_found(self):
        claim=self.reserve();self.ledger.provision(B,1000);self.ledger.open_job(B,'job',1000)
        for f in [lambda:self.ledger.request(B,'request'),lambda:self.ledger.cancel(B,'request'),lambda:self.ledger.start(B,claim)]:
            with self.assertRaises(DomainError) as e:f()
            self.assertEqual(e.exception.status,404)
        self.assertEqual(self.ledger.balance(B)['held'],0);self.assertEqual(self.ledger.events(B),[])
    def test_same_request_ids_are_namespaced_by_tenant(self):
        self.reserve();self.ledger.provision(B,1000);self.ledger.open_job(B,'job',1000);self.reserve(principal=B)
        self.assert_account(40,0);self.assertEqual(self.ledger.balance(B)['held'],40)
    def test_reader_and_anonymous_budget_access_denied(self):
        for p in [READER,None]:
            with self.assertRaises(DomainError):self.ledger.balance(p)
            with self.assertRaises(DomainError):self.ledger.provision(p,1000)
    def test_budget_cannot_silently_expand_after_restart(self):
        with self.assertRaises(DomainError):self.ledger.provision(A,2000)
        with self.assertRaises(DomainError):self.ledger.open_job(A,'job',2000)
        self.assert_account(0,0)
    def test_concurrent_duplicate_has_exactly_one_owner(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            claims=list(pool.map(lambda _:self.reserve(),range(16)))
        self.assertEqual(sum(c is not None for c in claims),1);self.assert_account(40,0)
    def test_competing_jobs_cannot_overspend_account(self):
        self.ledger.open_job(A,'other',1000)
        def submit(i):
            try:return self.reserve('c'+str(i),job='job' if i%2 else 'other') is not None
            except DomainError as e:self.assertEqual(e.code,'simulation_budget_exceeded');return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:result=list(pool.map(submit,range(40)))
        self.assertEqual(sum(result),25);self.assert_account(1000,0)
    def test_event_write_failure_rolls_back_entire_settlement(self):
        claim=self.reserve();n=self.ledger.start(A,claim)
        with self.ledger.transaction() as db:db.execute("CREATE TRIGGER fail_event BEFORE INSERT ON provider_budget_events WHEN NEW.kind='usage_settled' BEGIN SELECT RAISE(ABORT,'synthetic rollback'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.ledger.record(A,claim,n,3,2,H('r'))
        self.assert_account(40,0);self.assertEqual(self.ledger.request(A,'request')['state'],'in_flight')
    def test_application_database_is_never_migrated(self):
        target=Path(self.tmp.name)/'application.sqlite3'
        with sqlite3.connect(target) as db:db.execute('CREATE TABLE documents(id TEXT)')
        before=target.read_bytes()
        with self.assertRaises(DomainError):SimulationBudgetLedger(target)
        self.assertEqual(target.read_bytes(),before)
    def test_unsafe_database_and_identifier_rejected(self):
        with self.assertRaises(DomainError):SimulationBudgetLedger(Path(self.tmp.name)/'file:remote')
        with self.assertRaises(DomainError):self.reserve('../request')

    def test_parallel_settlement_charges_once(self):
        claim=self.reserve();n=self.ledger.start(A,claim)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _:self.ledger.record(A,claim,n,3,2,H('same')),range(8)))
        self.ledger.finish(A,claim,'completed');self.assert_account(0,5)
    def test_separate_processes_share_one_atomic_budget(self):
        import subprocess,sys
        code="""import sys,hashlib
from apps.api.models import Principal
from apps.api.provider_budget import SimulationBudgetLedger,Reservation
from apps.api.errors import DomainError
p=Principal('synthetic-process','A','worker');db=SimulationBudgetLedger(sys.argv[1]);count=0
for i in range(20):
 k=sys.argv[2]+str(i)
 try:db.reserve(p,'job',k,hashlib.sha256(k.encode()).hexdigest(),Reservation(10,10,1000000,1000000,2,100));count+=1
 except DomainError:pass
print(count)
"""
        processes=[subprocess.Popen([sys.executable,'-B','-c',code,str(self.path),key],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for key in ['proc-a','proc-b']]
        counts=[]
        for proc in processes:
            stdout,stderr=proc.communicate(timeout=20);self.assertEqual(proc.returncode,0,stderr);counts.append(int(stdout))
        self.assertEqual(sum(counts),25);self.assert_account(1000,0)
    def test_sqlite_integrity_and_owner_token_not_persisted(self):
        claim=self.reserve();self.assertNotIn(claim.token,repr(claim))
        with self.ledger.transaction() as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        self.assertNotIn(claim.token,self.path.read_bytes().decode(errors='ignore'))


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.ledger=SimulationBudgetLedger(Path(self.tmp.name)/'costs.sqlite3')
        self.ledger.provision(A,1_000_000);self.ledger.open_job(A,'job',1_000_000)
        self.payload={'synthetic':'input only'};self.approval=approved_simulation_input(A,self.payload)
    def tearDown(self):self.tmp.cleanup()
    def gateway(self,responses,**settings):
        self.transport=FakeTransport(responses)
        return ProviderSafetyGateway(ProviderSettings(provider='openai',model='fake-model-v1',**settings),self.ledger,self.transport)
    def run_call(self,gateway,request='r',validate=lambda v:v):
        return gateway.invoke(A,'job',request,'rag',self.payload,self.approval,validate)
    def test_success_receipt_never_claims_real_or_semantic_approval(self):
        value,receipt=self.run_call(self.gateway([complete({'synthetic':'candidate'})]))
        self.assertEqual(value,{'synthetic':'candidate'});self.assertEqual(receipt.actual_spent_micro,0)
        self.assertTrue(receipt.test_only);self.assertFalse(receipt.publishable)
        self.assertEqual(receipt.semantic_verification,'NOT_VERIFIED');self.assertEqual(self.ledger.balance(A)['held'],0)
    def test_default_real_transport_and_spoofed_transport_rejected(self):
        settings=ProviderSettings(provider='openai',model='fake-model-v1')
        class Spoof:
            network_access=False
            def send(self,*_):raise AssertionError('must never execute')
        for transport in [None,BlockedTransport(),Spoof()]:
            with self.assertRaises(DomainError):ProviderSafetyGateway(settings,self.ledger,transport)
    def test_subclass_and_callback_fake_transports_rejected(self):
        class Evil(FakeTransport):pass
        with self.assertRaises(DomainError):ProviderSafetyGateway(ProviderSettings(provider='openai',model='fake-model-v1'),self.ledger,Evil([complete()]))
        with self.assertRaises(DomainError):FakeTransport([lambda:None])
    def test_environment_flags_and_synthetic_key_cannot_enable_network(self):
        with patch.dict('os.environ',{'PAID_CALLS_APPROVED':'true','OPENAI_API_KEY':'synthetic-key-only'}):
            with self.assertRaises(ValidationError):ProviderSettings(provider='openai',model='fake-model-v1',real_calls_enabled=True)
            with self.assertRaises(DomainError):ProviderSafetyGateway(ProviderSettings(provider='openai',model='fake-model-v1'),self.ledger)
    def test_provider_ssrf_model_url_key_and_redirect_configuration_rejected(self):
        for changes in [{'provider':'http://169.254.169.254'},{'endpoint':'https://untrusted.invalid'},{'model':'../../admin'},{'model':'fake?key=value'},{'api_key':'synthetic-secret'}]:
            values={'provider':'openai','model':'fake-model-v1',**changes}
            with self.assertRaises(ValidationError):ProviderSettings(**values)
    def test_only_fixed_https_endpoints_constructed(self):
        s=ProviderSettings(provider='google',model='fake-model-v1')
        self.assertEqual(s.endpoint('workflow'),'https://generativelanguage.googleapis.com/v1beta/models/fake-model-v1:generateContent')
        self.assertTrue(s.endpoint('embedding').endswith(':embedContent'))
        with self.assertRaises(DomainError):s.endpoint('arbitrary')
    def test_manifest_and_tenant_checked_before_budget_or_send(self):
        g=self.gateway([complete()]);other=approved_simulation_input(B,self.payload)
        for approval in [other,self.approval.model_copy(update={'payload_sha256':H('wrong')})]:
            with self.assertRaises(DomainError):g.invoke(A,'job','r','rag',self.payload,approval,lambda v:v)
        self.assertEqual(self.transport.calls,0);self.assertEqual(self.ledger.events(A),[])
    def test_unapproved_classification_rejected(self):
        with self.assertRaises(ValidationError):ApprovedSimulationInput(institution_id='A',payload_sha256=H('x'),classification='private',manifest_version='test')
    def test_input_byte_token_limit_before_any_send(self):
        with self.assertRaises(DomainError):self.run_call(self.gateway([complete()],max_input_tokens=2))
        self.assertEqual(self.transport.calls,0);self.assertEqual(self.ledger.events(A),[])
    def test_per_request_budget_blocks_before_any_send(self):
        with self.assertRaises(DomainError):self.run_call(self.gateway([complete()],request_cap_micro=1))
        self.assertEqual(self.transport.calls,0)
    def test_account_insufficient_blocks_before_any_send(self):
        self.ledger.provision(B,1);self.ledger.open_job(B,'job',1)
        g=self.gateway([complete()])
        with self.assertRaises(DomainError):g.invoke(B,'job','r','rag',self.payload,approved_simulation_input(B,self.payload),lambda v:v)
        self.assertEqual(self.transport.calls,0)
    def test_delay_within_timeout_and_late_response_timeout(self):
        g=self.gateway([complete().model_copy(update={'delay_seconds':.005})],timeout_seconds=.05)
        self.run_call(g);self.assertEqual(self.transport.calls,1)
        g=self.gateway([complete().model_copy(update={'delay_seconds':.05})],timeout_seconds=.005)
        with self.assertRaises(DomainError) as e:self.run_call(g,request='late')
        self.assertEqual(e.exception.code,'provider_timeout_unknown_charge')
        self.assertEqual(self.ledger.request(A,'late')['state'],'uncertain')
    def test_local_connection_failure_releases_reservation(self):
        g=self.gateway([FakeResponse(failure='connect')])
        with self.assertRaises(DomainError):self.run_call(g)
        self.assertEqual(self.ledger.balance(A)['held'],0);self.assertEqual(self.ledger.balance(A)['spent'],0)
    def test_timeout_uncertainty_blocks_automatic_retry(self):
        g=self.gateway([FakeResponse(failure='timeout'),complete()])
        with self.assertRaises(DomainError):self.run_call(g)
        self.assertEqual(self.transport.calls,1);self.assertGreater(self.ledger.balance(A)['held'],0)
    def test_429_then_success_exactly_two_attempts(self):
        g=self.gateway([error(429),complete()]);self.run_call(g)
        self.assertEqual(self.transport.calls,2);self.assertEqual(self.ledger.request(A,'r')['attempts'],2)
    def test_503_then_success_exactly_two_attempts(self):
        g=self.gateway([error(503),complete()]);self.run_call(g)
        self.assertEqual(self.transport.calls,2);self.assertEqual(self.ledger.balance(A)['held'],0)
    def test_retry_limit_exhaustion_releases_known_free_holds(self):
        g=self.gateway([error(503),error(503),complete()])
        with self.assertRaises(DomainError):self.run_call(g)
        self.assertEqual(self.transport.calls,2);self.assertEqual(self.ledger.balance(A)['held'],0)
    def test_retry_after_is_bounded_and_observed(self):
        g=self.gateway([error(429).model_copy(update={'retry_after_seconds':.02}),complete()]);start=time.monotonic();self.run_call(g)
        self.assertGreaterEqual(time.monotonic()-start,.018)
        with self.assertRaises(ValidationError):FakeResponse(retry_after_seconds=999.0)
    def test_unauthorized_and_redirect_and_nonretryable_http_do_not_retry(self):
        for n,status in enumerate([401,403,404,302,500]):
            g=self.gateway([error(status),complete()])
            with self.subTest(status=status),self.assertRaises(DomainError):self.run_call(g,request='r'+str(n))
            self.assertEqual(self.transport.calls,1)
    def test_unknown_error_usage_does_not_assume_no_charge(self):
        g=self.gateway([error(503,known=False),complete()])
        with self.assertRaises(DomainError):self.run_call(g)
        self.assertEqual(self.transport.calls,1);self.assertEqual(self.ledger.request(A,'r')['state'],'uncertain')
    def test_incomplete_model_refusal_extra_fields_rejected(self):
        variants=[{'status':'incomplete'},{'status':'refusal'},{'model':'other-model'},{'publishable':True}]
        for n,change in enumerate(variants):
            g=self.gateway([complete(**change)])
            with self.assertRaises(DomainError):self.run_call(g,request='r'+str(n))
            self.assertEqual(self.ledger.request(A,'r'+str(n))['state'],'uncertain')
    def test_duplicate_json_nonfinite_oversized_malformed_and_usage_boolean(self):
        bodies=[b'{',b'{"usage":{},"usage":{}}',b'{"output":NaN}',b'x'*262145,
                encoded({'status':'complete','model':'fake-model-v1','output':{},'usage':{'input_tokens':True,'output_tokens':0}})]
        for n,body in enumerate(bodies):
            g=self.gateway([FakeResponse(body=body)])
            with self.assertRaises(DomainError):self.run_call(g,request='r'+str(n))
            self.assertEqual(self.transport.calls,1)
    def test_usage_over_cap_never_settled_as_small_charge(self):
        g=self.gateway([complete(usage={'input_tokens':1,'output_tokens':30})],max_output_tokens=10)
        with self.assertRaises(DomainError):self.run_call(g)
        self.assertEqual(self.ledger.balance(A)['spent'],0);self.assertGreater(self.ledger.balance(A)['held'],0)
    def test_rejected_grounding_retains_used_simulated_cost_only(self):
        g=self.gateway([complete()])
        def reject(_):raise ValueError('SYNTHETIC_PRIVATE_MARKER')
        with self.assertRaises(DomainError) as e:self.run_call(g,validate=reject)
        self.assertNotIn('SYNTHETIC_PRIVATE_MARKER',str(e.exception));self.assertEqual(e.exception.code,'provider_output_rejected')
        self.assertEqual(self.ledger.balance(A)['held'],0);self.assertGreater(self.ledger.balance(A)['spent'],0)
        self.assertEqual(self.ledger.request(A,'r')['state'],'rejected')
    def test_duplicate_gateway_request_never_sends_again(self):
        g=self.gateway([complete(),complete()]);self.run_call(g)
        spent=self.ledger.balance(A)['spent']
        with self.assertRaises(DomainError):self.run_call(g)
        self.assertEqual(self.transport.calls,1);self.assertEqual(self.ledger.balance(A)['spent'],spent)
    def test_concurrent_same_request_never_sends_twice(self):
        g=self.gateway([complete().model_copy(update={'delay_seconds':.02}),complete()])
        def invoke(_):
            try:self.run_call(g);return True
            except DomainError:return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:result=list(pool.map(invoke,range(4)))
        self.assertEqual(sum(result),1);self.assertEqual(self.transport.calls,1)
    def test_cancellation_during_send_discards_late_result(self):
        g=self.gateway([complete().model_copy(update={'delay_seconds':.08})])
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(self.run_call,g)
            for _ in range(100):
                if self.transport.calls:break
                time.sleep(.001)
            self.ledger.cancel_job(A,'job')
            with self.assertRaises(DomainError):future.result()
        self.assertEqual(self.ledger.request(A,'r')['state'],'uncertain')
    def test_no_secret_source_or_exception_body_in_logs_repr_or_events(self):
        marker='SYNTHETIC_PRIVATE_MARKER';g=self.gateway([FakeResponse(body=encoded({'error':marker}))])
        records=[]
        class Capture(logging.Handler):
            def emit(self,record):records.append(record.getMessage())
        handler=Capture();logging.getLogger().addHandler(handler)
        try:
            with self.assertRaises(DomainError) as e:self.run_call(g)
        finally:logging.getLogger().removeHandler(handler)
        self.assertNotIn(marker,str(e.exception));self.assertNotIn(marker,json.dumps(self.ledger.events(A)))
        self.assertNotIn(marker,repr(FakeResponse(body=marker.encode())))
        self.assertNotIn(marker,repr(SimulationRequest('https://api.openai.com/v1/responses',H('x'),marker.encode())))
        self.assertFalse(any(marker in r for r in records))
    def test_fake_paths_make_zero_socket_or_dns_calls(self):
        with patch('socket.getaddrinfo',side_effect=AssertionError('DNS forbidden')),patch('socket.socket.connect',side_effect=AssertionError('network forbidden')):
            self.run_call(self.gateway([error(429),complete()]))

    def test_model_copy_cannot_enable_real_or_private_inputs(self):
        settings=ProviderSettings(provider='openai',model='fake-model-v1').model_copy(update={'real_calls_enabled':True})
        with self.assertRaises(DomainError):ProviderSafetyGateway(settings,self.ledger,FakeTransport([complete()]))
        g=self.gateway([complete()]);bad=self.approval.model_copy(update={'classification':'private'})
        with self.assertRaises(DomainError):g.invoke(A,'job','r','rag',self.payload,bad,lambda v:v)
        self.assertEqual(self.transport.calls,0)
    def test_model_copy_cannot_poison_fake_response(self):
        for change in [{'delay_seconds':-1.0},{'status':'redirect'},{'failure':'custom_callback'}]:
            with self.assertRaises(DomainError):FakeTransport([complete().model_copy(update=change)])
    def test_expired_lease_during_send_conservatively_holds(self):
        now=[1000.0];self.ledger.clock=lambda:now[0];self.ledger.ttl=1
        g=self.gateway([complete().model_copy(update={'delay_seconds':.05})],timeout_seconds=.2)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(self.run_call,g)
            for _ in range(100):
                if self.transport.calls:break
                time.sleep(.001)
            now[0]+=2
            with self.assertRaises(DomainError):future.result()
        self.assertEqual(self.ledger.request(A,'r')['state'],'uncertain')

    def test_transport_replacement_after_construction_still_denied(self):
        g=self.gateway([complete()])
        class NotFake:
            def send(self,*args):raise AssertionError('must not run')
        g.transport=NotFake()
        with self.assertRaises(DomainError):self.run_call(g)
        self.assertEqual(self.ledger.events(A),[])


class AdapterTests(unittest.TestCase):
    def setUp(self):
        import test_parsing as fixtures
        import test_chunking
        from test_workflow_discovery import synthetic_hwpx
        from apps.api.workflow_snapshot import WorkflowInputService
        from apps.api.workflow_offline_adapter import DeterministicWorkflowAdapter
        fixtures.ParsingIntegrationTests.setUp(self)
        self.prepare=test_chunking.ChunkIntegrationTests.prepare.__get__(self)
        self.meta,_,self.items=self.prepare(synthetic_hwpx(['업무명: 별빛 자료 확인','1. 담당자는 별빛신청서를 제출한다.','2. 검토자는 자료를 확인한다.']),'provider-synthetic.hwpx')
        self.app.state.service.activate(self.principal,self.meta['document_id'],self.meta['id'])
        self.inputs=WorkflowInputService(self.app.state.chunks)
        self.snapshot=self.inputs.capture(self.principal,self.meta['document_id'],self.meta['id'])
        self.output=DeterministicWorkflowAdapter().extract(self.snapshot).model_dump(mode='json')
        self.permission=SimulationDocumentPermission(institution_id='A',document_id=self.meta['document_id'],version_id=self.meta['id'],original_sha256=self.meta['sha256'],classification='synthetic')
        self.ledger=SimulationBudgetLedger(self.root/'simulation-costs.sqlite3');self.ledger.provision(self.principal,3_000_000);self.ledger.open_job(self.principal,'job',1_000_000)
    def tearDown(self):
        import test_parsing as fixtures
        fixtures.ParsingIntegrationTests.tearDown(self)
    def upload(self,*args,**kwargs):
        import test_parsing as f
        return f.ParsingIntegrationTests.upload(self,*args,**kwargs)
    def parse(self,*args,**kwargs):
        import test_parsing as f
        return f.ParsingIntegrationTests.parse(self,*args,**kwargs)
    def route(self,*args,**kwargs):
        import test_parsing as f
        return f.ParsingIntegrationTests.route(self,*args,**kwargs)
    def gateway(self,output,**settings):
        self.transport=FakeTransport([complete(output)])
        return ProviderSafetyGateway(ProviderSettings(provider='openai',model='fake-model-v1',max_input_tokens=100_000,**settings),self.ledger,self.transport)
    def workflow(self,output=None,permission=None):
        return FakeWorkflowExtractionAdapter(self.inputs,self.gateway(self.output if output is None else output),self.principal,'job','workflow',permission or self.permission)
    def test_workflow_protocol_and_existing_discovery_engine(self):
        from apps.api.workflow_discovery import WorkflowDiscoveryEngine
        result=WorkflowDiscoveryEngine(self.inputs,self.workflow()).run(self.principal,self.snapshot)
        self.assertEqual(result.extraction.model_dump(mode='json'),self.output)
        self.assertEqual(result.validation.semantic_verification,'NOT_VERIFIED');self.assertFalse(result.validation.publishable)
        self.assertTrue(result.test_only);self.assertEqual(self.transport.calls,1)
    def test_workflow_separate_contract_return_is_preserved(self):
        from apps.api.workflow_contracts import WorkflowExtraction
        result=self.workflow().extract(self.snapshot)
        self.assertIsInstance(result,WorkflowExtraction);self.assertIsNone(result.workflows[0].steps[0].deadline)
    def test_workflow_unsupported_deadline_is_rejected(self):
        bad=copy.deepcopy(self.output);bad['workflows'][0]['steps'][0]['deadline']={**bad['workflows'][0]['steps'][0]['label'],'text':'반드시 999일 이내 처리한다.'}
        with self.assertRaises(DomainError):self.workflow(bad).extract(self.snapshot)
        self.assertEqual(self.ledger.request(self.principal,'workflow')['state'],'rejected')
    def test_workflow_fake_citation_and_wrong_span_rejected(self):
        for n,field in enumerate(['chunk_id','block_id','end']):
            bad=copy.deepcopy(self.output);c=bad['workflows'][0]['title']['evidence'][0];c[field]=999 if field=='end' else 'not-real'
            adapter=FakeWorkflowExtractionAdapter(self.inputs,self.gateway(bad),self.principal,'job','bad'+str(n),self.permission)
            with self.assertRaises(DomainError):adapter.extract(self.snapshot)
    def test_workflow_extra_flags_duplicate_ids_and_command_output_rejected(self):
        for n,kind in enumerate(['flags','id','command']):
            bad=copy.deepcopy(self.output)
            if kind=='flags':bad['semantic_verification']='VERIFIED'
            elif kind=='id':bad['workflows'][0]['steps'][1]['id']=bad['workflows'][0]['steps'][0]['id']
            else:bad['tools']=[{'command':'do-not-execute-synthetic'}]
            adapter=FakeWorkflowExtractionAdapter(self.inputs,self.gateway(bad),self.principal,'job','bad'+str(n),self.permission)
            with self.assertRaises(DomainError):adapter.extract(self.snapshot)
    def test_workflow_foreign_permission_fails_before_send(self):
        adapter=self.workflow(permission=self.permission.model_copy(update={'institution_id':'B'}))
        with self.assertRaises(DomainError):adapter.extract(self.snapshot)
        self.assertEqual(self.transport.calls,0)
    def test_stale_generation_or_retired_document_fails_before_send(self):
        adapter=self.workflow();self.app.state.service.deregister(self.principal,self.meta['document_id'])
        with self.assertRaises(DomainError):adapter.extract(self.snapshot)
        self.assertEqual(self.transport.calls,0)
    def test_workflow_partial_requested_scope_cannot_reference_other_chunks(self):
        adapter=self.workflow()
        with self.assertRaises(DomainError):adapter.extract_with_coverage(self.snapshot,('invented-chunk',))
        self.assertEqual(self.transport.calls,0)
    def rag(self,output,permissions=None):
        return FakeLLMAdapter(self.app.state.chunks,self.gateway(output),self.principal,'job','rag',permissions or [self.permission])
    def first_claim(self):
        span=next(s for s in self.items[0]['evidence']['spans'] if s['source_kind']=='original_text')
        return {'text':span['quote'],'chunk_ids':[self.items[0]['chunk_id']]}
    def test_rag_generation_contract_and_original_grounding(self):
        from apps.api.rag_adapters import Generation
        result=self.rag({'status':'candidate','claims':[self.first_claim()]}).generate('합성 자료 확인',self.items)
        self.assertIsInstance(result,Generation);self.assertEqual(result.claims[0].text,self.first_claim()['text'])
    def test_rag_unsupported_claim_unknown_ref_and_false_status(self):
        for n,kind in enumerate(['claim','reference','status']):
            claim=self.first_claim()
            if kind=='claim':claim['text']='존재하지 않는 의무 999일'
            if kind=='reference':claim['chunk_ids']=['invented']
            adapter=FakeLLMAdapter(self.app.state.chunks,self.gateway({'status':'insufficient_evidence' if kind=='status' else 'candidate','claims':[claim]}),self.principal,'job','rag'+str(n),[self.permission])
            with self.assertRaises(DomainError):adapter.generate('합성 자료 확인',self.items)
    def test_rag_no_context_returns_insufficient_without_send(self):
        adapter=self.rag({'status':'insufficient_evidence','claims':[]})
        self.assertEqual(adapter.generate('합성 질문',[]).status,'insufficient_evidence');self.assertEqual(self.transport.calls,0)
    def test_rag_mixed_tenant_or_noncanonical_context_fails_before_send(self):
        for kind in ['tenant','text']:
            items=copy.deepcopy(self.items)
            if kind=='tenant':items[0]['evidence']['organization_id']='B'
            else:items[0]['text']='SYNTHETIC_UNSUPPORTED_TEXT'
            adapter=self.rag({'status':'candidate','claims':[self.first_claim()]})
            with self.assertRaises(DomainError):adapter.generate('합성 질문',items)
            self.assertEqual(self.transport.calls,0)
    def embedding(self,output,principal=None,permission=None):
        permission=permission or SimulationEmbeddingPermission(institution_id='A',text_hashes=(H('합성 문서'),),classification='synthetic')
        return FakeEmbeddingAdapter(self.gateway(output),principal or self.principal,'job','embedding',permission,4)
    def test_embedding_count_dimension_norm_and_test_only_spec(self):
        adapter=self.embedding([[1,1,1,1]])
        self.assertEqual(adapter.embed(['합성 문서']),[[.5,.5,.5,.5]]);self.assertTrue(adapter.spec.test_only)
        self.assertEqual(adapter.spec.provider,'fake-openai')
    def test_embedding_invalid_count_dimension_zero_nan_bool(self):
        for n,output in enumerate([[],[[1,1]],[[0,0,0,0]],[[True,1,1,1]]]):
            permission=SimulationEmbeddingPermission(institution_id='A',text_hashes=(H('합성 문서'),),classification='synthetic')
            adapter=FakeEmbeddingAdapter(self.gateway(output),self.principal,'job','embed'+str(n),permission,4)
            with self.assertRaises(DomainError):adapter.embed(['합성 문서'])
    def test_embedding_foreign_permission_or_unapproved_text_before_send(self):
        with self.assertRaises(DomainError):self.embedding([[1,1,1,1]],principal=B)
        adapter=self.embedding([[1,1,1,1]])
        with self.assertRaises(DomainError):adapter.embed(['허용되지 않은 합성 문서'])
        self.assertEqual(self.transport.calls,0)
    def test_document_permission_model_copy_private_classification_rejected(self):
        adapter=self.workflow(permission=self.permission.model_copy(update={'classification':'private'}))
        with self.assertRaises(DomainError):adapter.extract(self.snapshot)
        self.assertEqual(self.transport.calls,0)
    def test_missing_current_chunk_generation_is_unverified_and_never_sent(self):
        adapter=self.workflow()
        with self.app.state.service.repo.transaction() as db:
            db.connection.execute('DELETE FROM chunk_current WHERE version_id=?',(self.meta['id'],))
        with self.assertRaises(DomainError):adapter.extract(self.snapshot)
        self.assertEqual(self.transport.calls,0);self.assertEqual(self.ledger.events(self.principal),[])
    def test_retired_during_fake_inference_discards_output_but_settles_usage(self):
        gateway=self.gateway(self.output)
        gateway.transport=FakeTransport([complete(self.output).model_copy(update={'delay_seconds':.08})])
        adapter=FakeWorkflowExtractionAdapter(self.inputs,gateway,self.principal,'job','retired',self.permission)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(adapter.extract,self.snapshot)
            for _ in range(200):
                if gateway.transport.calls:break
                time.sleep(.001)
            self.app.state.service.deregister(self.principal,self.meta['document_id'])
            with self.assertRaises(DomainError):future.result()
        row=self.ledger.request(self.principal,'retired');self.assertEqual(row['state'],'rejected')
        self.assertEqual(row['held'],0);self.assertGreater(row['spent'],0)
    def test_model_command_text_never_executes(self):
        bad=copy.deepcopy(self.output);bad['tools']=[{'command':'SYNTHETIC_DO_NOT_EXECUTE'}]
        with patch('os.system',side_effect=AssertionError('must not execute')) as system:
            with self.assertRaises(DomainError):self.workflow(bad).extract(self.snapshot)
            system.assert_not_called()
    def test_inactive_version_permission_cannot_access_current_context(self):
        adapter=self.rag({'status':'candidate','claims':[self.first_claim()]},permissions=[self.permission.model_copy(update={'version_id':'wrong-version'})])
        with self.assertRaises(DomainError):adapter.generate('합성 질문',self.items)
        self.assertEqual(self.transport.calls,0)
    def test_existing_real_provider_guard_remains_closed(self):
        from apps.api.rag_service import RAGService
        from apps.api.rag_adapters import DeterministicEmbedding
        from apps.api.workflow_discovery import WorkflowDiscoveryEngine
        from apps.api.workflow_offline_adapter import DeterministicWorkflowAdapter
        real=DeterministicEmbedding();real.spec=real.spec.model_copy(update={'test_only':False})
        with self.assertRaises(DomainError):RAGService(self.app.state.chunks,real)
        real_workflow=DeterministicWorkflowAdapter();real_workflow.network_access=True
        with self.assertRaises(DomainError):WorkflowDiscoveryEngine(self.inputs,real_workflow)


if __name__=='__main__':unittest.main()
