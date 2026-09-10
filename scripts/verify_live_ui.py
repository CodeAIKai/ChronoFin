"""Real browser upload and live Hy3 response verification. No mocked model."""
import datetime
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright
from verify_ui import browser_options

ROOT=Path(__file__).resolve().parents[1]

def main():
    checks=[];errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(**browser_options());page=browser.new_page(viewport={'width':1440,'height':1000},accept_downloads=True)
        page.on('pageerror',lambda e:errors.append(str(e)))
        try:
            page.goto('http://127.0.0.1:8787',wait_until='networkidle');page.wait_for_function("document.querySelector('#case').options.length===20")
            page.select_option('#mode','pdf');page.locator('#pdfFile').set_input_files(ROOT/'data/cache/native_expansion/tencent25q2.pdf')
            page.locator('#question').fill('腾讯2025年第二季度收入、经营盈利和资本开支如何变化？比较IFRS与非IFRS口径，并说明不能由此确认的AI投资回报。')
            page.locator('#cutoff').fill('2025-09-01')
            page.screenshot(path=str(ROOT/'audit/live_pdf_upload.png'),full_page=True)
            with page.expect_response(lambda r:r.url.endswith('/api/ask_pdf'),timeout=240000) as pending:page.locator('#go').click()
            response=pending.value;data=response.json()
            (ROOT/'audit/live_pdf_result.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
            assert response.status==200 and data['status']=='ok',data.get('error')
            page.wait_for_selector('#download');page.wait_for_function("document.querySelector('#go').disabled===false")
            assert data['record']['source_document']['metadata_identity']=='pinned_official'
            assert data['record']['source_document']['pages']==9
            assert data['semantic']['trace']['model']=='hy3'
            assert data['scorecard']['score'] is None
            assert data['record']['extraction_audit']['facts_accepted']>0
            page.screenshot(path=str(ROOT/'audit/live_pdf_answer.png'),full_page=True)
            checks.append({'check':'real_pdf_upload_to_hy3_to_source_audit','pass':True,'source':'tencent25q2','facts':data['record']['extraction_audit']['facts_accepted']})
            page.locator('.ref').first.click();page.get_by_text('PDF 原文片段 · 已核验连续匹配',exact=True).first.wait_for()
            page.screenshot(path=str(ROOT/'audit/live_pdf_evidence.png'),full_page=True)
            checks.append({'check':'native_pdf_quote_navigation','pass':True})
            page.get_by_role('button',name='03 十维审计').click();assert page.locator('.dim').count()==10
            page.get_by_text('已核查原文支持；重要信息覆盖、反证完整性与未知边界仍需独立参考，不汇总总分。',exact=True).wait_for()
            page.screenshot(path=str(ROOT/'audit/live_pdf_partial_audit.png'),full_page=True)
            checks.append({'check':'no_gold_live_audit_reports_unknown_dimensions','pass':True})
            page.get_by_role('button',name='01 研究结论').click()
            with page.expect_download() as info:page.locator('#download').click()
            exported=json.loads(Path(info.value.path()).read_text());assert exported==data
            checks.append({'check':'live_record_download_matches_response','pass':True})
            page.select_option('#mode','live');page.locator('#question').fill('根据已有资料，写一段关于AI基础设施资本投入与电力供应约束的谨慎研究摘要。');page.locator('#cutoff').fill('2025-06-01')
            with page.expect_response(lambda r:r.url.endswith('/api/ask'),timeout=240000) as pending:page.locator('#go').click()
            response=pending.value;data=response.json();(ROOT/'audit/live_custom_result.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
            assert response.status==200 and data['status']=='ok',data.get('error')
            assert data['scorecard']['score'] is None and data['semantic']['trace']['model']=='hy3'
            page.wait_for_function("document.querySelector('#go').disabled===false");page.screenshot(path=str(ROOT/'audit/live_custom_answer.png'),full_page=True)
            checks.append({'check':'real_custom_question_hy3_call','pass':True})
        except Exception as e:
            page.screenshot(path=str(ROOT/'audit/live_ui_failure.png'),full_page=True)
            checks.append({'check':'live_flow','pass':False,'error':str(e)[:1200]})
        browser.close()
    result={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'checks':checks,'browser_page_errors':errors,
            'pass':bool(checks) and all(c['pass']for c in checks) and not errors,'mocked_model':False}
    (ROOT/'audit/ui_live_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False,indent=2))
    raise SystemExit(not result['pass'])

if __name__=='__main__':main()
