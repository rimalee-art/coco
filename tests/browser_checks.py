"""Functional checks: python3 tests/browser_checks.py (requires Playwright and Chromium)."""
import datetime
from functools import partial
import http.server
import json
from pathlib import Path
import tempfile
import threading
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args): pass


def main():
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), partial(Quiet, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{server.server_port}'
    with sync_playwright() as pw, tempfile.TemporaryDirectory() as temp:
        browser = pw.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
        errors = []
        def page():
            ctx = browser.new_context(viewport={'width':390, 'height':844})
            p = ctx.new_page()
            p.on('pageerror', lambda e: errors.append(str(e)))
            p.goto(url)
            p.evaluate('navigator.serviceWorker.ready')
            return p
        def home(p): p.locator('[data-go-home]').first.click()
        def year(p, y=2026, mock=False):
            p.locator('[data-mode="year"]').click()
            p.locator(f'[data-action="year:{y}"]').click()
            if mock: p.locator('[data-year-study="mock"]').click()
        def seed(p, values):
            p.evaluate('values=>{localStorage.clear();for(const [k,v] of Object.entries(values))localStorage.setItem(k,JSON.stringify(v))}', values)
            p.reload()
        def choose(p, id, original):
            p.evaluate(r'''({id, original})=>{
                const norm=s=>s.replace(/\s/g,'');
                const q=window.QUIZ_DATA.questions.find(q=>q.id===id);
                const b=[...document.querySelectorAll('.choice')].find(b=>norm(b.lastElementChild.textContent)===norm(q.choices[original-1]));
                if(!b || b.disabled)throw new Error('Choice unavailable');b.click();document.querySelector('#checkBtn').click();
            }''', {'id':id,'original':original})
        def wrongbook(p): return p.evaluate('JSON.parse(localStorage.getItem("mindGrowWrongBook"))')
        p=page()
        seed(p, {'mindGrowWrongBook':[{'id':'2026-2-A-26','availableOn':'2020-01-01'}]})
        p.locator('[data-elective="청소년수련활동론"]').click()
        assert p.locator('#reviewCard').is_hidden()
        p.locator('[data-elective="청소년이해론"]').click()
        assert p.locator('#reviewCard').is_visible()
        for width in [390,1440]:
            p.set_viewport_size({'width':width,'height':900})
            cards=p.locator('.mode-grid > .mode-card:visible')
            assert cards.first.get_attribute('id')=='reviewCard'
            a=cards.nth(0).bounding_box();bpos=cards.nth(1).bounding_box()
            assert (a['y']<bpos['y'] if width==390 else a['x']<bpos['x'])
        p.set_viewport_size({'width':390,'height':844})
        print('PASS due review is the first visible card on mobile and desktop')
        seed(p, {'mindGrowWrongBook':[{'id':'2026-1-A-1','availableOn':'2020-01-01'}]})
        p.locator('[data-mode="review"]').click(); choose(p,'2026-1-A-1',1); choose(p,'2026-1-A-1',5)
        book=wrongbook(p)
        assert len(book)==1 and book[0]['reviewStage']==0
        assert book[0]['availableOn'] > book[0]['reviewStartedOn']
        p.locator('#quitBtn').click();assert p.locator('#resultScore').inner_text()=='0%'
        assert '재시도 포함 정답: 1문제' in p.locator('#resultCopy').inner_text()
        print('PASS elective filtering, legacy wrong-book compatibility, retry does not complete review')
        p=page()
        p.clock.install(time=datetime.datetime(2030,10,30,12,tzinfo=datetime.timezone.utc))
        seed(p, {'mindGrowWrongBook':[{'id':'2026-1-A-1','availableOn':'2030-10-31','reviewStage':0,'reviewStartedOn':'2030-10-30'}]})
        for day,due,stage in [('2030-10-31','2030-11-02',1),('2030-11-02','2030-11-06',2),('2030-11-06','2030-11-13',3),('2030-11-13',None,4)]:
            p.clock.set_fixed_time(datetime.datetime.fromisoformat(day+'T12:00:00+00:00'));p.reload()
            p.locator('[data-mode="review"]').click();choose(p,'2026-1-A-1',5)
            book=wrongbook(p)
            if due: assert book[0]['availableOn']==due and book[0]['reviewStage']==stage
            else: assert book==[]
        print('PASS 1/3/7/14-day schedule and final removal only after four first-try successes')
        p=page();year(p);p.locator('[data-action="year-subject:발달심리"]').click()
        choose(p,'2026-1-A-1',5);p.locator('#quitBtn').click()
        assert p.locator('#resultScore').inner_text()=='100%'
        assert '4% (1 / 25문제)' in p.locator('#resultCopy').inner_text()
        p.locator('#retryBtn').click();choose(p,'2026-1-A-1',5);p.locator('#quitBtn').click();home(p)
        assert p.locator('#solvedCount').inner_text()=='1 / 1,050문제'
        year(p);p.locator('[data-action="year-subject:발달심리"]').click();p.locator('#quitBtn').click()
        assert p.locator('#resultScore').inner_text()=='—'
        print('PASS partial-result accuracy, zero-answer result, repeated question coverage')
        p=page();year(p,mock=True);p.locator('[data-action="mock-session:1"]').click()
        def complete_mock(p, session, count):
            p.evaluate(r'''({session,count})=>{
                const norm=s=>s.replace(/\s/g,'');
                for(let i=0;i<count;i++) {
                    const tags=document.querySelectorAll('#questionMeta .tag');
                    const n=Number(tags[1].textContent.match(/· (\d+)번/)[1]);
                    const q=window.QUIZ_DATA.questions.find(q=>q.id===`2026-${session}-A-${n}`);
                    const actual=[...document.querySelectorAll('.choice span:last-child')].map(b=>norm(b.textContent));
                    if(actual.some((v,i)=>v!==norm(q.choices[i])))throw new Error('Mock choices out of order');
                    document.querySelector(`.choice[data-choice="${q.answers[0]}"]`).click();document.querySelector('#checkBtn').click();
                }
            }''',{'session':session,'count':count})
        complete_mock(p,1,100);p.reload();year(p,mock=True)
        assert '완료' in p.locator('[data-action="mock-session:1"]').inner_text()
        p.locator('[data-action="mock-session:2"]').click();complete_mock(p,2,50)
        p.locator('#finalExamBtn').click();assert p.locator('#resultScore').inner_text()=='100점'
        p.reload();year(p,mock=True);p.locator('[data-action="mock-final"]').click();assert p.locator('#resultScore').inner_text()=='100점'
        home(p);year(p,mock=True);p.locator('[data-action="mock-session:1"]').click();p.locator('#quitBtn').click()
        assert p.locator('#finalExamBtn').is_hidden()
        p.reload();year(p,mock=True);p.locator('[data-action="mock-session:2"]').click();p.locator('#quitBtn').click()
        p.locator('#finalExamBtn').click();assert p.locator('#resultScore').inner_text()=='0점'
        assert p.evaluate('JSON.parse(localStorage.getItem("mindGrowMockExamHistory")).length')==4
        print('PASS full 100+50 mock, original choices, reload recovery, final-results access and attempt isolation')
        home(p)
        with p.expect_download() as dl: p.locator('#exportRecordsBtn').click()
        path=Path(temp)/'backup.json';dl.value.save_as(path)
        backup=json.loads(path.read_text());assert backup['format']=='mind-grow-records'
        seed(p, {'mindGrowHistory':{'solved':3,'correct':2}})
        p.once('dialog',lambda d:d.accept())
        p.locator('#importRecordsFile').set_input_files(str(path))
        p.wait_for_function('window.MindGrowRecords && window.MindGrowRecords.read("mindGrowMockExamHistory",[]).length===4')
        assert p.evaluate('JSON.parse(localStorage.getItem("mindGrowMockExamHistory")).length')==4
        before=p.evaluate('JSON.stringify({...localStorage})')
        p.once('dialog',lambda d:d.dismiss())
        p.locator('#importRecordsFile').set_input_files(str(path))
        p.wait_for_timeout(200)
        assert p.evaluate('JSON.stringify({...localStorage})')==before
        bad=Path(temp)/'bad.json';bad.write_text(json.dumps({'format':'mind-grow-records','version':1,'records':{'mindGrowHistory':{'solved':None,'correct':0}}}))
        p.locator('#importRecordsFile').set_input_files(str(bad));p.wait_for_function('document.querySelector("#recordStatus").textContent.includes("현재 기록")')
        assert p.evaluate('JSON.stringify({...localStorage})')==before
        # A one-time write failure midway through import must roll back the old records.
        outcome=p.evaluate('''backup=>{
            backup=structuredClone(backup);backup.records.mindGrowMockExamHistory[0].id='changed-import-record';
            const before=JSON.stringify({...localStorage});const native=Storage.prototype.setItem;let count=0;
            Storage.prototype.setItem=function(k,v){if(++count===2)throw new DOMException('Full','QuotaExceededError');return native.call(this,k,v)};
            let rejected=false;try{MindGrowRecords.restore(backup)}catch(e){rejected=true}finally{Storage.prototype.setItem=native}
            return rejected && before===JSON.stringify({...localStorage});
        }''',backup)
        assert outcome
        assert p.evaluate('MindGrowRecords.validateBackup({format:"mind-grow-records",version:1,records:{}}).version')==1
        print('PASS backup export/import, empty backup validation, invalid import rejection and failed import rollback')
        p=page();p.evaluate('localStorage.setItem("mindGrowHistory","bad-json");localStorage.setItem("mindGrowWrongBook","null");localStorage.setItem("mindGrowMockExamHistory", "[{}]")');p.reload()
        assert p.locator('#bankCount').inner_text()=='1,050'
        assert p.locator('#storageNotice').is_visible()
        archive=p.evaluate('MindGrowRecords.backup()');assert archive['recovery']['mindGrowHistory']=='bad-json'
        assert archive['recovery']['mindGrowWrongBook']=='null'
        assert archive['recovery']['mindGrowMockExamHistory']=='[{}]'
        print('PASS corrupted JSON/types recover without startup failure; originals preserved in backup')
        p=page();p.evaluate("() => {Storage.prototype.setItem=function(){throw new DOMException('Denied','SecurityError')}}")
        year(p);p.locator('[data-action="year-subject:발달심리"]').click();choose(p,'2026-1-A-1',5)
        assert p.locator('#storageNotice').is_visible()
        assert p.evaluate('MindGrowRecords.backup().records.mindGrowHistory.solved')==1
        print('PASS storage write failure: learning continues with warning and exportable in-memory records')
        p=page();p.add_init_script("Storage.prototype.getItem=function(){throw new DOMException('Denied','SecurityError')}");p.reload()
        assert p.locator('#bankCount').inner_text()=='1,050'
        assert p.locator('#storageNotice').is_visible()
        print('PASS unavailable storage reads do not prevent startup')
        p=page();c=p.context;c.set_offline(True);p.reload()
        assert p.evaluate('window.MindGrowRecords !== undefined')
        assert p.locator('.mode-grid .mode-card:visible').first.inner_text().find('오늘의 20문제')!=-1
        assert not p.evaluate('document.documentElement.scrollWidth>innerWidth')
        assert not errors,errors
        print('PASS offline startup, mobile layout, daily card first; no browser errors')
        browser.close()
    server.shutdown()

if __name__ == '__main__': main()
