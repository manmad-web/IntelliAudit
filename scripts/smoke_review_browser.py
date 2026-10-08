"""Optional full reviewer-browser check using only temporary synthetic records.

Run manually: python scripts/smoke_review_browser.py
Requires the existing Playwright dependency and Chromium. Set REVIEW_BROWSER to
a Chromium executable when it is not on PATH. This script uses local reviewer
identities; authenticated curator/reviewer role, CSRF and session boundaries are
covered by tests/test_hosted_access.py. It never connects to the hosted database.
"""
import json
import os
import shutil
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dashboard.review_store import ReviewStore
from dashboard.server import Store, handler_for


def saved_events(reviews):
    with reviews.connect() as connection:
        return [json.loads(row[0]) for row in connection.execute(
            'SELECT payload FROM events ORDER BY rowid').fetchall()]


def identify(page, reviewer_id, name):
    page.locator('#reviewer-id').fill(reviewer_id)
    page.locator('#reviewer-name').fill(name)
    page.locator('#qualification').fill('Synthetic software test only; not an accountant annotation')
    page.locator('#apply-identity').click()
    page.wait_for_selector('#annotation-form[data-stage="blind"]')


def fill_initial(page, reason):
    page.locator('[name="judgement"]').select_option('insufficient_evidence')
    page.locator('[name="confidence"]').select_option('low')
    page.locator('[name="reasoning"]').fill(reason)
    page.locator('[name="missing_information"]').fill('Synthetic test: source evidence not independently checked.')


def main():
    with tempfile.TemporaryDirectory(prefix='intelliaudit-browser-qa-') as temporary:
        folder = Path(temporary)
        reviews = ReviewStore(folder / 'synthetic-only.sqlite3')
        handler = handler_for(Store(), reviews=reviews)
        handler.log_message = lambda *args: None
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        errors = []
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    executable_path=os.environ.get('REVIEW_BROWSER') or shutil.which('chromium') or shutil.which('chromium-browser'),
                    headless=True, args=['--no-sandbox'])
                page = browser.new_page(viewport={'width': 1512, 'height': 1080})
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{server.server_port}/')
                page.wait_for_selector('.case')
                assert page.locator('.case').count() == 20
                expect(page.locator('#case-detail')).to_contain_text('Income Statement')
                expect(page.locator('#case-detail')).to_contain_text('US GAAP')
                expect(page.locator('#case-detail')).to_contain_text('Currency')
                expect(page.locator('#case-detail')).to_contain_text('Synthetic case information')
                assert page.locator('.statement-table tbody tr').count() > 0
                assert page.locator('.proposal').count() == 0

                # The guide and fictional practice cannot create formal records.
                page.locator('#guide-button').click()
                expect(page.locator('#guide-dialog')).to_be_visible()
                expect(page.locator('#guide-dialog')).to_contain_text('not actual invoices')
                page.keyboard.press('Escape')
                expect(page.locator('#guide-dialog')).not_to_be_visible()
                page.locator('#practice-button').click()
                expect(page.locator('#case-detail')).to_contain_text('Fictional practice')
                fill_initial(page, 'Synthetic practice response only; no domain assessment performed.')
                page.locator('#annotation-form button[type="submit"]').click()
                expect(page.locator('#practice-feedback')).to_be_visible()
                assert saved_events(reviews) == []
                page.locator('#practice-return').click()
                page.wait_for_selector('.statement-table')
                assert page.locator('.case').count() == 20

                identify(page, 'browser-qa-a', 'Synthetic test operator A')
                case_ids = page.locator('.case').evaluate_all('(buttons) => buttons.map(button => button.dataset.id)')
                first_case = case_ids[0]

                # Optional standards remain unresolved; only Stage A is required.
                assert not page.locator('.standards-details').evaluate('(element) => element.open')
                assert page.locator('[name="authority_disposition"]').input_value() == 'unresolved'
                assert page.locator('[name="authority_currency"]').input_value() == 'unresolved'
                assert page.locator('[name="citations"]').input_value() == ''
                fill_initial(page, 'Synthetic initial response A; browser draft persistence check.')
                page.locator('.case-quality summary').click()
                page.locator('[name="case_quality_flags"][value="source_unclear"]').check()
                page.locator('[name="case_quality_notes"]').fill('Software fixture: source not checked by an accountant.')
                page.reload()
                page.wait_for_selector('#annotation-form[data-stage="blind"]')
                expect(page.locator('[name="reasoning"]')).to_have_value('Synthetic initial response A; browser draft persistence check.')
                assert page.locator('[name="case_quality_flags"][value="source_unclear"]').is_checked()

                for index, case_id in enumerate(case_ids):
                    if index:
                        page.locator(f'.case[data-id="{case_id}"]').click()
                        page.wait_for_selector('#annotation-form[data-stage="blind"]')
                        fill_initial(page, f'Synthetic initial response A case {index + 1}; no accounting review performed.')
                    page.locator('#annotation-form button[type="submit"]').click()
                    if index < 19:
                        page.wait_for_selector('#reveal-button')
                        assert page.locator('.proposal').count() == 0
                        expect(page.locator('#reveal-button')).to_be_disabled()
                    else:
                        page.wait_for_selector('.proposal')
                        expect(page.locator('.comparison')).to_contain_text('Your preserved initial answer')
                        expect(page.locator('#annotation-form')).to_have_attribute('data-stage', 'verification')
                expect(page.locator('#protocol-progress')).to_contain_text('20 of 20')
                initial = [event for event in saved_events(reviews) if event['stage'] == 'blind']
                assert len(initial) == 20
                assert all(event['reviewer_id'] == 'browser-qa-a' for event in initial)
                first_record = next(event for event in initial if event['case_id'] == first_case)
                assert first_record['annotation']['authority_currency'] == 'unresolved'

                # Proposal feedback is separate and immediate after the twentieth case.
                page.locator(f'.case[data-id="{first_case}"]').click()
                page.wait_for_selector('.proposal')
                expect(page.locator('.comparison')).to_contain_text('Your preserved initial answer')
                expect(page.locator('.comparison')).to_contain_text('Generated proposal')
                page.locator('[name="disposition"]').select_option('revise')
                page.locator('[name="judgement"]').select_option('ambiguous')
                page.locator('[name="reasoning"]').fill('Synthetic separate feedback only: leave the source question unresolved.')
                page.locator('#annotation-form button[type="submit"]').click()
                expect(page.locator('#case-detail')).to_contain_text('Latest separate proposal feedback saved')
                after = saved_events(reviews)
                assert next(event for event in after if event['event_id'] == first_record['event_id']) == first_record
                feedback = next(event for event in after if event['stage'] == 'verification')
                assert feedback['annotation']['disposition'] == 'revise'
                assert feedback['annotation']['judgement'] == 'ambiguous'
                page.reload()
                page.wait_for_selector('.proposal')
                expect(page.locator('#case-detail')).to_contain_text('Latest separate proposal feedback saved')
                assert len(saved_events(reviews)) == len(after)

                with page.expect_download() as download:
                    page.locator('#export-button').click()
                backup = folder / 'backup.json'
                download.value.save_as(backup)
                envelope = json.loads(backup.read_text(encoding='utf-8'))
                assert envelope['scope']['dataset'] == 'pilot-v2'
                assert envelope['protocol_plan']['version'] == 2
                assert sum(event['stage'] == 'blind' for event in envelope['events']) == 20
                assert not any(event['stage'] == 'repeat' for event in envelope['events'])
                page.locator('#import-file').set_input_files(backup)
                expect(page.locator('#status')).to_contain_text('Backup imported')
                assert len(saved_events(reviews)) == len(after)

                # A second local identity cannot inherit drafts or bypass its first pass.
                identify(page, 'browser-qa-b', 'Synthetic test operator B')
                expect(page.locator('[name="reasoning"]')).to_have_value('')
                expect(page.locator('[name="missing_information"]')).to_have_value('')
                assert not page.locator('[name="case_quality_flags"][value="source_unclear"]').is_checked()
                assert page.locator('.proposal').count() == 0
                fill_initial(page, 'Synthetic separate reviewer B; no accounting assessment performed.')
                page.locator('#annotation-form button[type="submit"]').click()
                page.wait_for_selector('#reveal-button')
                expect(page.locator('#reveal-button')).to_be_disabled()
                reviewer_b = [event for event in saved_events(reviews) if event['reviewer_id'] == 'browser-qa-b']
                assert len(reviewer_b) == 1
                assert next(event for event in saved_events(reviews) if event['event_id'] == first_record['event_id']) == first_record

                page.screenshot(path=str(folder / 'desktop.png'), full_page=True)
                page.set_viewport_size({'width': 390, 'height': 844})
                assert page.evaluate('() => document.documentElement.scrollWidth <= window.innerWidth')
                page.locator('#guide-button').click()
                expect(page.locator('#guide-dialog')).to_be_visible()
                assert page.evaluate('() => document.documentElement.scrollWidth <= window.innerWidth')
                page.locator('#close-guide').click()
                page.screenshot(path=str(folder / 'mobile.png'), full_page=True)
                assert not errors, errors
                browser.close()
            print('PASS: fictional practice creates no records; 20 initial cases unlock immediate proposal comparison; unresolved optional standards; draft persistence; separate feedback and immutable first answer; export/import; reviewer isolation; desktop/mobile; zero JavaScript errors. Only temporary synthetic review records used.')
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    main()
