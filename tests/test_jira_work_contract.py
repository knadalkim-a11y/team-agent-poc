"""Real loopback HTTP contracts for Jira v2 reads; only synthetic data/PATs.

This exercises urllib request/response parsing, pagination and attachment access,
not a live company Jira or document content adequacy review.
"""
import asyncio
import importlib.util
import json
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / 'agent-pack/skills/jira-read/scripts/jira_tool.py'
SPEC = importlib.util.spec_from_file_location('ees_jira_work_contract', PATH)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class JiraWorkHTTPTests(unittest.TestCase):
    def setUp(self):
        self.calls = []; self.mode = ''; self.total = 3; self.attachments = 1
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_GET(self):
                split = urllib.parse.urlsplit(self.path)
                query = urllib.parse.parse_qs(split.query)
                owner.calls.append({'path': split.path, 'query': query, 'auth': self.headers.get('Authorization'), 'range': self.headers.get('Range')})
                status, payload, content_type = owner.respond(split.path, query)
                raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
                self.send_response(status); self.send_header('Content-Type', content_type); self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(self.close)
        self.base = f'http://127.0.0.1:{self.server.server_port}/jira'
        self.tool = module.Tools(); self.tool.valves.ENABLED = True; self.tool.valves.ALLOW_HTTP = True
        self.tool.valves.JIRA_BASE_URL = self.base; self.tool.valves.ALLOWED_PROJECTS = 'APPX,OTHER'; self.tool.valves.MAX_RESULTS = 2
        guard = patch.object(module, '_encryption_enabled', return_value=True); guard.start(); self.addCleanup(guard.stop)
        self.user = {'id': 'synthetic-author', 'valves': self.tool.UserValves(PAT='synthetic-private-pat')}
    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2)
    def attachment(self, id='21'):
        return {'id': id, 'filename': 'design.txt', 'size': 12, 'mimeType': 'text/plain', 'content': self.base + '/secure/attachment/'+id+'/design.txt'}
    def issue(self, number):
        return {'id': str(number), 'key': f'APPX-{number}', 'fields': {'project': {'key': 'APPX'}, 'summary': 'Synthetic CR', 'status': {'id': '11', 'name': 'Review', 'statusCategory': {'key': 'indeterminate'}}, 'assignee': None, 'priority': None, 'updated': '2026-10-01T00:00:00Z', 'duedate': None, 'customfield_12001': '2026-10-01', 'attachment': [self.attachment(str(21+i)) for i in range(self.attachments)]}}
    def respond(self, path, query):
        if path.endswith('/myself'): return 200, {'name': 'synthetic-author', 'active': True}, 'application/json'
        if path.endswith('/project'): return 200, [{'key': 'APPX', 'name': 'Actual project'}, {'key': 'HIDDEN', 'name': 'Do not disclose'}], 'application/json'
        if path.endswith('/statuses'): return (403, {}, 'application/json') if self.mode=='statuses_denied' else (200, [{'id': '1', 'statuses': [{'id': '11', 'name': 'Review'}, {'id': '12', 'name': 'Ready'}]}], 'application/json')
        if path.endswith('/field'): return 200, [{'id': 'customfield_12001', 'name': 'Deployment date', 'searchable': True, 'schema': {'type': 'date'}}, {'id': 'created', 'name': 'Created', 'searchable': True, 'schema': {'type': 'datetime'}}, {'id': 'customfield_12002', 'name': 'Not a date', 'schema': {'type': 'string'}}], 'application/json'
        if path.endswith('/search'):
            start = int(query['startAt'][0]); amount = int(query['maxResults'][0]); total = self.total
            if start and self.mode=='second_denied': return 403, {}, 'application/json'
            if start and self.mode=='changed_total': total += 1
            issues = [self.issue(i+1) for i in range(start, min(start+amount, total))]
            if self.mode=='missing_page' and start: issues=[]
            if self.mode=='duplicate_page' and start: issues=[self.issue(1)]
            if self.mode=='wrong_project' and issues: issues[0]['fields']['project']['key']='OTHER'
            if self.mode=='missing_attachment' and issues: issues[0]['fields'].pop('attachment')
            return 200, {'startAt': start, 'maxResults': amount, 'total': total, 'issues': issues}, 'application/json'
        if '/issue/' in path:
            number=int(path.rsplit('-',1)[1]); value=self.issue(number)
            if query.get('fields')==['project']: value={'key':f'APPX-{number}','fields':{'project':{'key':'APPX'}}}
            elif self.mode=='missing_attachment': value['fields'].pop('attachment')
            elif self.mode=='no_attachments': value['fields']['attachment']=[]
            return 200,value,'application/json'
        if '/rest/api/2/attachment/' in path:
            if self.mode=='attachment_metadata_denied': return 403, {}, 'application/json'
            item=self.attachment(path.rsplit('/',1)[1])
            if self.mode=='evil_attachment': item['content']='https://outside.example.invalid/secure/attachment/21/design.txt'
            if self.mode=='encoded_path': item['content']=self.base+'/secure/attachment/21/..%2fsecret'
            return 200,item,'application/json'
        if '/secure/attachment/' in path:
            if self.mode=='attachment_denied': return 403, b'', 'application/octet-stream'
            if self.mode=='attachment_html': return 200, b'<html>login</html>', 'text/html'
            return 206,b'S','application/octet-stream'
        return 404,{},'application/json'
    def call(self, operation='search_crs', **values):
        args={'project_key':'APPX','status_ids':['11'],'date_field':'customfield_12001','start_date':'2026-10-01','end_date':'2026-10-02','start_at':0} if operation=='search_crs' else {}
        result=self.tool._run(operation,self.user,**{**args,**values})
        self.assertNotIn('synthetic-private-pat',json.dumps(result))
        return result
    def test_real_http_metadata_uses_actual_allowed_visible_keys_statuses_and_date_schema(self):
        value=self.call('project_metadata',project_key='APPX')
        self.assertTrue(value['ok']); self.assertEqual(value['projects'],[{'id':'APPX','name':'Actual project'}]); self.assertEqual([x['id'] for x in value['statuses']],['11','12'])
        self.assertEqual([x['id'] for x in value['date_fields']],['customfield_12001','created']); self.assertTrue(all(c['auth']=='Bearer synthetic-private-pat' for c in self.calls))
    def test_ems_is_not_a_default_project_and_injected_arguments_stop_before_http(self):
        for values in ({'project_key':'EMS'},{'status_ids':['11) OR project=OTHER']},{'date_field':'created OR project=OTHER'},{'start_date':'2026-10-01" OR 1=1'},{'start_at':-1}):
            self.assertFalse(self.call(**values)['ok'])
        self.assertEqual(self.calls,[])
    def test_metadata_denial_is_not_an_empty_successful_status_list(self):
        self.mode='statuses_denied'; value=self.call('project_metadata',project_key='APPX'); self.assertFalse(value['ok']); self.assertEqual(value['error']['code'],'permission_denied')
    def test_unknown_status_or_wrong_field_type_is_rejected_before_search(self):
        for args in ({'status_ids':['999']},{'date_field':'customfield_12002'}):
            self.assertFalse(self.call(**args)['ok'])
        self.assertFalse(any(c['path'].endswith('/search') for c in self.calls))
    def test_multiple_pages_produce_complete_list_and_exact_generated_jql(self):
        value=self.call(); self.assertEqual(value['status'],'complete'); self.assertEqual([v['key'] for v in value['issues']],['APPX-1','APPX-2','APPX-3'])
        pages=[c for c in self.calls if c['path'].endswith('/search')]; self.assertEqual([c['query']['startAt'] for c in pages],[['0'],['2']]); self.assertEqual(pages[0]['query']['jql'][0],'project = "APPX" AND status IN (11) AND cf[12001] >= "2026-10-01" AND cf[12001] < "2026-10-03" ORDER BY key ASC')
        self.assertFalse(value['content_reviewed']); self.assertIsNone(value['listing']['next_start_at'])
    def test_bounded_page_cap_stays_partial_and_exposes_real_continuation(self):
        self.tool.valves.MAX_CR_PAGES=1; value=self.call(); self.assertEqual(value['status'],'partial'); self.assertEqual(value['listing']['next_start_at'],2); self.assertEqual(value['listing']['total'],3)
        continuation=self.call(start_at=2); self.assertEqual(continuation['status'],'partial'); self.assertIsNone(continuation['listing']['next_start_at'])
    def test_missing_duplicate_changed_or_denied_page_never_becomes_complete(self):
        for mode in ('missing_page','duplicate_page','changed_total','second_denied'):
            with self.subTest(mode=mode):
                self.mode=mode; value=self.call(); self.assertEqual(value['status'],'partial'); self.assertTrue(value['errors']); self.assertEqual(len(value['issues']),2); self.assertIsNone(value['listing']['next_start_at'])
    def test_no_matching_issues_is_legitimate_empty_complete_result(self):
        self.total=0; value=self.call(); self.assertTrue(value['ok']); self.assertEqual(value['status'],'complete'); self.assertEqual(value['issues'],[])
    def test_cross_project_response_and_missing_attachment_field_are_not_complete(self):
        self.mode='wrong_project'; self.assertFalse(self.call()['ok']); self.mode='missing_attachment'; value=self.call(); self.assertEqual(value['status'],'partial'); self.assertTrue(value['errors'])
    def test_real_attachment_metadata_and_range_probe_do_not_claim_content_review(self):
        value=self.call('issue_attachments',issue_key='APPX-1'); self.assertEqual(value['completeness'],'complete'); self.assertEqual(value['attachments'][0]['accessibility'],'readable'); self.assertFalse(value['content_reviewed']); probes=[c for c in self.calls if '/secure/attachment/' in c['path']]; self.assertEqual(probes[0]['range'],'bytes=0-0')
    def test_missing_or_denied_attachment_is_distinct_from_absence(self):
        self.mode='missing_attachment'; missing=self.call('issue_attachments',issue_key='APPX-1'); self.assertFalse(missing['ok'])
        self.mode='no_attachments'; empty=self.call('issue_attachments',issue_key='APPX-1'); self.assertEqual(empty['completeness'],'complete'); self.assertEqual(empty['attachments'],[])
        self.mode='attachment_denied'; denied=self.call('issue_attachments',issue_key='APPX-1'); self.assertEqual(denied['completeness'],'partial'); self.assertEqual(denied['attachments'][0]['accessibility'],'denied')
    def test_foreign_or_encoded_attachment_url_never_receives_pat_or_download_request(self):
        for mode in ('evil_attachment','encoded_path'):
            self.mode=mode; self.calls.clear(); value=self.call('issue_attachments',issue_key='APPX-1'); self.assertEqual(value['completeness'],'partial'); self.assertEqual(value['attachments'][0]['error']['code'],'attachment_url_blocked'); self.assertFalse(any('/secure/attachment/' in c['path'] for c in self.calls))
    def test_attachment_html_login_response_and_metadata_denial_stay_partial(self):
        for mode in ('attachment_html','attachment_metadata_denied'):
            self.mode=mode; value=self.call('issue_attachments',issue_key='APPX-1'); self.assertEqual(value['completeness'],'partial'); self.assertNotEqual(value['attachments'][0]['accessibility'],'readable')
    def test_attachment_cap_and_personal_credentials_are_preserved(self):
        self.attachments=2; self.tool.valves.MAX_ATTACHMENTS=1; value=self.call('issue_attachments',issue_key='APPX-1'); self.assertEqual((value['total'],value['returned'],value['completeness']),(2,1,'partial'))
        self.calls.clear(); other={'id':'other','valves':self.tool.UserValves(PAT='synthetic-other-pat')}; self.tool._run('project_metadata',other,project_key=''); self.assertTrue(all(c['auth']=='Bearer synthetic-other-pat' for c in self.calls))
    def test_new_async_public_methods_round_trip_real_http(self):
        value=json.loads(asyncio.run(self.tool.jira_project_metadata(project_key='APPX',__user__=self.user))); self.assertTrue(value['ok']); self.assertTrue(value['date_fields'])

    def test_batch_attachments_preserve_each_requested_cr_and_same_id_provenance(self):
        result=self.call('cr_attachments',required_filenames=['design.txt'],issue_keys=['APPX-1','APPX-2'])
        self.assertTrue(result['ok']); self.assertEqual(result['completeness'],'complete')
        self.assertEqual([item['key'] for item in result['issues']],['APPX-1','APPX-2'])
        self.assertEqual([item['id'] for item in result['attachments']],['APPX-1:21','APPX-2:21'])
        self.assertFalse(result['content_reviewed']); self.assertEqual(result['requested'],['APPX-1','APPX-2'])
    def test_batch_budget_and_per_issue_denial_never_lose_required_cr(self):
        self.tool.valves.MAX_ATTACHMENTS=1
        result=self.call('cr_attachments',required_filenames=['design.txt'],issue_keys=['APPX-1','APPX-2'])
        self.assertEqual(result['completeness'],'partial'); self.assertEqual(result['returned'],2)
        self.assertEqual(result['issues'][1]['total'],1); self.assertEqual(result['issues'][1]['returned'],0)
        self.assertEqual(len([call for call in self.calls if call['range']]),1)
        self.mode='attachment_metadata_denied'
        result=self.call('cr_attachments',required_filenames=['design.txt'],issue_keys=['APPX-1','APPX-2'])
        self.assertEqual(result['status'],'partial'); self.assertEqual(len(result['issues']),2)
    def test_batch_scope_injection_duplicates_and_limits_reject_before_http(self):
        for keys in ([],['APPX-1','APPX-1'],['HIDDEN-1'],['APPX-1 OR true'],['APPX-'+str(i) for i in range(1,52)]):
            before=len(self.calls); result=self.call('cr_attachments',required_filenames=['design.txt'],issue_keys=keys)
            self.assertFalse(result['ok']); self.assertEqual(len(self.calls),before)

    def test_batch_required_names_are_explicit_and_missing_is_not_document_approval(self):
        result=self.call('cr_attachments',issue_keys=['APPX-1'],required_filenames=['design.txt','test.txt'])
        self.assertEqual([row['state'] for row in result['document_checks']],['present_readable','missing'])
        self.assertTrue(all(row['content_reviewed'] is False for row in result['document_checks']))
        self.assertEqual(result['completeness'],'complete')  # complete observation, not acceptable documents
        for names in ([],['design.txt','design.txt'],['../design.txt'],['a\\b'],['x']*21):
            before=len(self.calls); result=self.call('cr_attachments',issue_keys=['APPX-1'],required_filenames=names)
            self.assertFalse(result['ok']); self.assertEqual(len(self.calls),before)
