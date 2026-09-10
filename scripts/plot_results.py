"""Standalone measured research figures with exact source CSV tables."""
import csv,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1]
def load(n):return json.loads((ROOT/n).read_text())
def main():
    out=ROOT/'assets/figures';out.mkdir(parents=True,exist_ok=True)
    g=load('results/grounded/v1/summary.json');e=load('results/extended_analysis.json');h=load('results/external_human/v3/summary.json');n=load('results/native_validation/v2/summary.json')
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    data=[]
    def save(fig,name):fig.savefig(out/(name+'.png'),dpi=160);fig.savefig(out/(name+'.svg'));plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(11,4.8));methods=['full_context','counterbrief_first_pass','full_context_revision','counterbrief'];labels=['Full context','Counter: draft','Generic revision','Counter: revised'];cols=['#9aaba6','#93b5ad','#587b82','#117766']
    for ax,key,title in [(axs[0],'mean_score_failure_zero','Same judge / 15 questions'),(axs[1],'mean_pipeline_tokens','Generation + audit tokens')]:
        vals=[g['application']['evaluation/'+m][key]for m in methods];ax.bar(range(4),vals,color=cols);ax.set_xticks(range(4),labels,rotation=18,ha='right');ax.set_title(title)
        for i,v in enumerate(vals):ax.text(i,v*1.025,f'{v:.1f}',ha='center',fontsize=9)
        ax.set_ylim(0,max(vals)*1.15)
        for m,v in zip(methods,vals):data.append(['equal_call',m,key,v])
    axs[0].set_ylabel('Author diagnostic score (not accuracy)');axs[1].set_ylabel('Reported tokens / answer');fig.suptitle('Equal-call control and first-draft ablation');fig.tight_layout(rect=[0,.03,1,.95]);fig.text(.5,.01,'Author-visible regression; clustered CI for counter - generic: +0.193 to +11.643 points.',ha='center',fontsize=9);save(fig,'application_comparison')
    fig,axs=plt.subplots(1,2,figsize=(11,4.5))
    for i,m in enumerate(['holistic_v2','operational_v3']):
        x=h['groups']['new_response_validation/'+m];v=x['accuracy_failure_wrong']*100;axs[0].bar(i,v,color=cols[[2,3][i]]);axs[0].text(i,v+2,f'{v:.1f}% / k={x["cohen_kappa"]:.3f}',ha='center');data.append(['external_new_response',m,'accuracy_percent',v])
    axs[0].set_xticks([0,1],['Holistic','Operational']);axs[0].set_ylim(0,110);axs[0].set_title('Published human labels / 150 responses');axs[0].set_ylabel('3-class agreement (%)')
    for i,m in enumerate(['legacy','anchored']):
        x=e['order_reliability'][m];axs[1].bar(i,x['mean_range'],color=cols[[2,3][i]]);axs[1].text(i,x['mean_range']+.3,f'{x["mean_range"]:.3f}',ha='center');data.append(['order_reliability',m,'mean_range',x['mean_range']])
    axs[1].set_xticks([0,1],['Legacy judge','Evidence anchored']);axs[1].set_ylim(0,11);axs[1].set_ylabel('Mean score range (lower is better)');axs[1].set_title('6 answers x 4 order/repeat treatments');fig.tight_layout(rect=[0,.06,1,1]);fig.text(.5,.01,'External validation shares development questions; 15/150 final disagreements. Anchored judge still has a 6-point range.',ha='center',fontsize=9);save(fig,'reliability_and_completion')
    controls={x['id'].removesuffix('_v2_control'):x['score']for x in n['details']if x['id'].endswith('_v2_control')};final=load('results/native_pdf/v5/summary.json')['records'];fig,ax=plt.subplots(figsize=(11,4.8))
    for i,x in enumerate(final):
        ax.plot([i,i],[controls[x['id']],x['score']],color='#b3c4bf');ax.scatter(i,controls[x['id']],color='#587b82',label='Saved v2 / final judge'if i==0 else None);ax.scatter(i,x['score'],color='#117766',marker='D',label='Final v5 / same judge'if i==0 else None)
        data.extend([['native_same_judge',x['id'],'saved_v2',controls[x['id']]],['native_same_judge',x['id'],'final_v5',x['score']]])
    ax.set_xticks(range(len(final)),[x['id']for x in final],rotation=30,ha='right');ax.set_ylim(0,110);ax.set_ylabel('Author diagnostic score');ax.set_title('Five official PDFs / 12-question regression (same final judge)');ax.legend(loc='lower right');fig.tight_layout(rect=[0,.045,1,1]);fig.text(.5,.01,'Known failure: AP02 repeats the same input in a growth calculation despite a high judge score. No expert blind labels.',ha='center',fontsize=9);save(fig,'native_same_judge')
    with(out/'measured_results.csv').open('w',newline='')as f:w=csv.writer(f);w.writerow(['experiment','condition','metric','value']);w.writerows(data)
    # Replace obsolete early quota-subset CSVs with the exact current table.
    for name in ['application_comparison.csv','reliability_and_completion.csv']:(out/name).write_bytes((out/'measured_results.csv').read_bytes())
    print('Three figures generated as PNG/SVG with measured_results.csv; no model calls.')
if __name__=='__main__':main()
