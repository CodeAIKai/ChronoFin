"""Capture final real browser flows and encode an under-two-minute replay GIF."""
import argparse,datetime,hashlib,json,time
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright
from verify_ui import browser_options
ROOT=Path(__file__).resolve().parents[1]
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--url',default='http://127.0.0.1:8787');args=ap.parse_args()
    directory=ROOT/'assets/demo_frames';directory.mkdir(parents=True,exist_ok=True);shots=[];errors=[];started=time.monotonic()
    with sync_playwright()as p:
        browser=p.chromium.launch(**browser_options());page=browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1);page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(args.url,wait_until='networkidle');page.wait_for_function("document.querySelector('#case').options.length===20");page.evaluate('document.fonts.ready')
        def capture(label,seconds):
            path=directory/f'{len(shots)+1:02d}.png';page.screenshot(path=str(path));shots.append({'file':str(path.relative_to(ROOT)),'action':label,'display_ms':seconds*1000,'capture_elapsed_seconds':round(time.monotonic()-started,3),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        def load(case,native=False):
            page.select_option('#mode','native_replay'if native else'replay')
            if native:page.select_option('#nativeCase',case)
            else:page.select_option('#run','v3');page.select_option('#case',case);page.select_option('#strategy','counterbrief')
            page.locator('#go').click();page.wait_for_function("!document.querySelector('#go').disabled && !!document.querySelector('#download') && document.querySelector('#message').textContent.includes('研究简报已载入')");page.evaluate('window.scrollTo(0,0)')
        capture('个人活動作品：选择真实Hy3响应回放或实时PDF分析',5)
        load('TC01',True);capture('腾讯中文9页原生PDF：AI投入、经营改善与现金约束',8)
        page.locator('.ref').first.click();page.locator('#evidence').scroll_into_view_if_needed();capture('点击引用：登记原件身份、原文连续片段与页码',8)
        page.get_by_role('button',name='03 十维审计').click();page.evaluate('window.scrollTo(0,0)');capture('十维诊断及可核查证据，声明非专家评分',6)
        load('AP02',True);page.locator('#brief .review-note').first.wait_for();capture('主动展示高分失效案例：同一数值重复用于跨期增长，提示复核',7)
        load('TC02',True);capture('披露日前案例：不使用尚未公开的财报作答',7)
        load('D04');capture('行业研究：IEA能源与AI，支持依据与反证',7)
        page.locator('.ref').first.click();capture('行业资料账本：来源、可知时间及核对转述',6)
        load('D01');page.get_by_role('button',name='03 十维审计').click();page.get_by_text('需复核：同一回答的评委分数出现分歧',exact=True).wait_for();capture('评委也会出错：相同答案55至100，保留分歧和换算依据',8)
        page.get_by_role('button',name='04 实验对照').click();page.get_by_role('heading',name='相同调用预算对照').wait_for();page.evaluate('window.scrollTo(0,0)');capture('实验记录：主应用60/60、主评估30/30',5)
        page.get_by_role('heading',name='相同调用预算对照').scroll_into_view_if_needed();capture('公平比较：通用二次修订与反证修订，共同裁判与tokens',7)
        page.get_by_role('heading',name='外部人工标签 · 新回答验证').scroll_into_view_if_needed();capture('公开人工标签一致率78%到90%，注明共享问题限制',7)
        page.get_by_role('heading',name='原生 PDF · 全部案例').scroll_into_view_if_needed();capture('原生PDF完整12题，低分同样展示',6)
        load('TC01',True)
        with page.expect_download()as info:page.locator('#download').click()
        exported=json.loads(Path(info.value.path()).read_text());assert exported['record']['pipeline']=='native_pdf_v5'
        capture('下载原始回答、引用、模型判断与调用记录，便于独立复查',4);browser.close()
    if errors:raise RuntimeError(errors)
    frames=[]
    for shot in shots:
        with Image.open(ROOT/shot['file'])as im:frames.append(im.convert('RGB').quantize(colors=192))
    gif=ROOT/'assets/chronofin_demo_actual.gif';frames[0].save(gif,save_all=True,append_images=frames[1:],duration=[s['display_ms']for s in shots],loop=0,optimize=True,disposal=2)
    out={'captured_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'capture_elapsed_seconds':round(time.monotonic()-started,3),'presentation_duration_ms':sum(s['display_ms']for s in shots),'frames':shots,'browser_page_errors':errors,'api_calls_during_recording':0,'gif_sha256':hashlib.sha256(gif.read_bytes()).hexdigest(),'note':'Actual Chromium actions on final native-v5 and brief-v3 saved real Hy3 responses. Frame reading durations are edited, not live API latency. Live PDF/custom model calls are independently proven in audit/ui_live_verification.json.'}
    (ROOT/'audit/demo_recording.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    lines=['# 实际演示说明','','文件：`assets/chronofin_demo_actual.gif`。最终工作台真实Chromium交互截图，共'+str(out['presentation_duration_ms']/1000)+'秒，少于2分钟。回放已保存的真实Hy3回答，帧停留时长为阅读而编辑，不代表实时接口速度。实时上传和自定义问题另有实际Hy3整链验收记录，无mock。','','| 时间段 | 实际画面 |','|---|---|'];t=0
    for s in shots:
        end=t+s['display_ms']/1000;lines.append(f"| {t:g}–{end:g}秒 | {s['action']} |");t=end
    lines+=['','所有截图哈希、录制时间及动作见 `audit/demo_recording.json`；原始PNG见 `assets/demo_frames/`。图中诊断分不是官方分或财务准确率，AP02失效计算及评委分歧在演示中明确展示。']
    (ROOT/'docs/演示说明.md').write_text('\n'.join(lines)+'\n');print(json.dumps({k:v for k,v in out.items()if k!='frames'},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
