"""Drive real local browser flows; save evidence of success and failure."""
import argparse
import datetime
import json
import os
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]

def browser_options():
    opt={'headless':True,'args':['--no-sandbox']}
    exe=os.environ.get('CHRONOFIN_CHROMIUM')
    if exe:opt['executable_path']=exe
    return opt

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--original',action='store_true');args=ap.parse_args()
    results=[];errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(**browser_options())
        page=browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1)
        page.on('pageerror',lambda e:errors.append(str(e)))
        try:
            page.goto('http://127.0.0.1:8787',wait_until='networkidle')
            page.wait_for_function("document.querySelector('#case').options.length===20")
            assert page.locator('#question').is_disabled()
            assert page.locator('#cutoff').is_disabled()
            results.append({'check':'replay_inputs_locked','pass':True})
            page.select_option('#run','v3');page.select_option('#case','D04');page.locator('#go').click()
            page.wait_for_selector('#download');page.evaluate('document.fonts.ready')
            assert page.locator('.claim').count()>0
            page.screenshot(path=str(ROOT/'audit/workbench_first.png'),full_page=True)
            results.append({'check':'actual_saved_hy3_brief_renders','pass':True,'claims':page.locator('.claim').count()})
            page.locator('.ref').first.click();assert page.locator('#evidence').is_visible()
            results.append({'check':'citation_navigation','pass':True})
            page.get_by_role('button',name='03 十维审计').click()
            assert page.locator('.dim').count()==10
            page.screenshot(path=str(ROOT/'audit/workbench_audit.png'),full_page=True)
            results.append({'check':'ten_dimension_audit','pass':True})
            page.select_option('#case','D01');page.locator('#go').click();page.wait_for_selector('#download')
            page.get_by_role('button',name='03 十维审计').click()
            page.get_by_text('需复核：同一回答的评委分数出现分歧',exact=True).wait_for()
            results.append({'check':'judge_disagreement_visible','pass':True})
            page.route('**/api/result?**',lambda route:route.fulfill(status=404,content_type='application/json',body=json.dumps({'error':'验收：不存在的结果记录'})))
            page.select_option('#case','E14');page.locator('#go').click();page.wait_for_selector('#message.error')
            assert page.locator('#brief').inner_text()=='此项未完成，尚无可展示的研究结论。'
            page.unroute('**/api/result?**')
            results.append({'check':'simulated_missing_record_clears_stale_answer','pass':True,'fixture':'Explicit 404 transport fixture; not a real failed experiment.'})
            page.select_option('#mode','live');assert page.locator('#question').is_enabled()
            assert page.locator('#importOptions').is_visible()
            results.append({'check':'live_custom_inputs_enabled','pass':True,'model_called':False})
            page.select_option('#mode','replay');page.select_option('#case','D04');page.locator('#go').click();page.wait_for_selector('#download')
            with page.expect_download() as info:page.locator('#download').click()
            data=json.loads(Path(info.value.path()).read_text());assert data['record']['answer']['claims']
            results.append({'check':'download_complete_record','pass':True})
            page.select_option('#mode','native_replay');page.select_option('#nativeCase','TC01');page.locator('#go').click()
            page.get_by_text('原生 PDF · 9 页',exact=False).wait_for()
            page.locator('.ref').first.click();assert page.locator('#evidence').is_visible()
            results.append({'check':'final_native_v5_chinese_pdf_replay','pass':True})
            page.select_option('#nativeCase','AP02');page.locator('#go').click();page.locator('#brief .review-note').first.wait_for()
            results.append({'check':'invalid_cross_period_calculation_warning_visible','pass':True})
            print('New application browser checks passed',flush=True)
        except Exception as e:
            page.screenshot(path=str(ROOT/'audit/ui_failure.png'),full_page=True)
            results.append({'check':'new_app_flow','pass':False,'error':str(e)[:1000]})
            print('New app failed:',type(e).__name__,flush=True)
        if args.original:
            try:
                page.goto('http://127.0.0.1:8501',wait_until='domcontentloaded')
                page.get_by_role('button',name='开始时点分析').wait_for(timeout=60000)
                page.get_by_role('button',name='开始时点分析').click()
                page.get_by_text('审计总分',exact=True).wait_for(timeout=60000)
                page.screenshot(path=str(ROOT/'audit/original_ui.png'),full_page=True)
                results.append({'check':'original_streamlit_analysis_flow','pass':True})
                print('Original application browser checks passed',flush=True)
            except Exception as e:
                page.screenshot(path=str(ROOT/'audit/original_ui_failure.png'),full_page=True)
                results.append({'check':'original_streamlit_analysis_flow','pass':False,'error':str(e)[:1000],
                                'page_text':page.locator('body').inner_text()[:1500]})
                print('Original app failed:',type(e).__name__,flush=True)
        browser.close()
    out={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'checks':results,'browser_page_errors':errors,
         'pass':bool(results) and all(x['pass'] for x in results) and not errors,
         'note':'Real Chromium clicks and response rendering; live API end-to-end traces are reported separately.'}
    (ROOT/'audit/ui_verification.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(out,ensure_ascii=False,indent=2))
    raise SystemExit(not out['pass'])

if __name__=='__main__':main()
