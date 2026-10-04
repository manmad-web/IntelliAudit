"""Optional live-browser integration check (requires Playwright and Chromium).

Uses a temporary review database; does not create real accountant annotations.
Run: python scripts/smoke_review_browser.py
Set REVIEW_BROWSER to a Chromium executable if it is not on PATH.
"""
import sys,tempfile,threading,json,os,shutil
from pathlib import Path
from http.server import ThreadingHTTPServer
from playwright.sync_api import sync_playwright, expect
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dashboard.server import Store, handler_for
from dashboard.review_store import ReviewStore
with tempfile.TemporaryDirectory() as td:
 server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(Store(),reviews=ReviewStore(Path(td)/'reviews.sqlite3')))
 thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 errors=[]
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(executable_path=os.environ.get('REVIEW_BROWSER') or shutil.which('chromium') or shutil.which('chromium-browser'),headless=True,args=['--no-sandbox'])
   page=browser.new_page(viewport={'width':1512,'height':1080})
   page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto(f'http://127.0.0.1:{server.server_port}')
   page.wait_for_selector('.case')
   expect(page.locator("#case-detail")).to_contain_text("Statement as presented")
   assert page.locator('.case').count()==20
   assert page.locator('.proposal').count()==0
   page.screenshot(path=str(Path(td)/'desktop.png'),full_page=True)
   page.locator('#reviewer-id').fill('browser-smoke-only')
   page.locator('#reviewer-name').fill('Synthetic test operator')
   page.locator('#qualification').fill('Software test only, not an accountant review')
   page.locator('#apply-identity').click()
   page.wait_for_selector('#annotation-form')
   for field,value in {'judgement':'insufficient_evidence','confidence':'low','evidence_sufficiency':'insufficient','authority_disposition':'unresolved','authority_currency':'unresolved'}.items():
    page.locator(f'[name="{field}"]').select_option(value)
   page.locator('[name="reasoning"]').fill('Synthetic browser test; no accounting assessment performed.')
   page.locator('#proof-sets input').first.check()
   page.locator('#annotation-form button[type=submit]').click()
   page.wait_for_selector('#reveal-button')
   assert page.locator('.proposal').count()==0
   page.reload()
   page.wait_for_selector('#reveal-button')
   assert page.locator('.proposal').count()==0
   page.locator('#reveal-button').click()
   page.wait_for_selector('.proposal')
   page.locator('[name="disposition"]').select_option('unresolved')
   page.locator('#annotation-form button[type=submit]').click()
   expect(page.locator("#case-detail")).to_contain_text("Latest reconciliation saved")
   with page.expect_download() as download:
    page.locator('#export-button').click()
   backup=Path(td)/'backup.json';download.value.save_as(backup)
   envelope=json.loads(backup.read_text());assert [e['stage'] for e in envelope['events']]==['blind','reveal','verification']
   page.locator('#import-file').set_input_files(backup)
   expect(page.locator("#status")).to_contain_text("Backup imported")
   assert page.locator('.proposal').count()==0
   # Switch reviewer: do not carry another person's draft into the new identity.
   page.locator('#reviewer-id').fill('second-test-operator');page.locator('#apply-identity').click()
   page.wait_for_selector('#annotation-form[data-stage=blind]')
   assert page.locator('[name="reasoning"]').input_value()==''
   page.set_viewport_size({'width':390,'height':844})
   page.screenshot(path=str(Path(td)/'mobile.png'),full_page=True)
   assert page.evaluate('() => document.documentElement.scrollWidth <= window.innerWidth')
   assert not errors,errors
   browser.close()
  print('PASS: 20-case live UI; blind submit/reload/reveal/reconcile/export/import; reviewer isolation; desktop/mobile; zero JS errors. Only temporary synthetic review DB used.')
 finally:
  server.shutdown();server.server_close();thread.join()
