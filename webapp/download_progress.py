"""Thread-safe byte telemetry; no simulated percentages or timers."""
import io
import time
from threading import RLock


class DownloadProgress:
    def __init__(self,total,cached,notify):
        self.total=total; self.cached=cached; self.notify=notify
        self.started=time.monotonic(); self.updated=self.started
        self.transfer_updated=self.started
        self.completed=0; self.transferred=0; self.last_emit=0
        self.samples=[]; self.lock=RLock()

    def reset_rate(self):
        """Do not treat restored disk data as freshly downloaded throughput."""
        with self.lock:
            self.samples=[(time.monotonic(),self.completed)]

    def update(self,kind,value):
        with self.lock:
            now=time.monotonic()
            if kind=='transfer':
                if value>self.transferred: self.transfer_updated=now
                self.transferred=max(self.transferred,value)
            else:
                if value>self.completed:
                    self.updated=now
                    self.samples.append((now,value))
                    self.samples=[sample for sample in self.samples if sample[0]>=now-20][-100:]
                self.completed=max(self.completed,value)
            if now-self.last_emit<0.25: return
            self.last_emit=now
            rate=0
            if len(self.samples)>1:
                first,last=self.samples[0],self.samples[-1]
                if last[0]>first[0]: rate=(last[1]-first[1])/(last[0]-first[0])
            remaining=max(0,self.total-self.cached-self.completed)
            elapsed=now-self.started
            self.notify({'kind':'download','message':'임베딩 모델 다운로드 중',
                'started':self.started,'updated':self.updated,'total':self.total,
                'transfer_updated':self.transfer_updated,
                'received':min(self.total,self.cached+self.completed),'cached':self.cached,
                'transferred':self.transferred,'speed':self.transferred/elapsed if elapsed>0 else 0,
                'eta':remaining/rate if rate>0 else None})

    def tqdm_class(self):
        from tqdm.auto import tqdm
        tracker=self
        class ReportingBar(tqdm):
            def __init__(self,*args,**kwargs):
                desc=kwargs.get('desc','')
                self.metric=('transfer' if desc.startswith('Downloading bytes') else
                             'completed' if desc.startswith('Reconstructing') else None)
                kwargs.pop('name',None)
                kwargs['file']=io.StringIO(); kwargs['disable']=False
                super().__init__(*args,**kwargs)

            def update(self,n=1):
                result=super().update(n)
                if self.metric: tracker.update(self.metric,self.n)
                return result
        return ReportingBar


def duration(seconds):
    if seconds is None: return '계산 중'
    seconds=max(0,int(seconds))
    hours,rest=divmod(seconds,3600); minutes,seconds=divmod(rest,60)
    return (f'{hours}시간 ' if hours else '')+f'{minutes}분 {seconds}초'


def progress_view(event,now=None):
    now=time.monotonic() if now is None else now
    stalled=now-event['updated']>10
    eta=None if stalled else event['eta']
    inactive=now-max(event['updated'],event['transfer_updated'])
    if inactive>30:
        status=f'최근 {int(inactive)}초 동안 전송·파일 준비 진행 보고가 없습니다. 네트워크 응답 또는 재시도를 기다리는 중일 수 있습니다.'
    elif stalled:
        status='데이터 전송 중 · 파일 준비 진행률은 내려받은 데이터가 반영될 때 갱신됩니다.'
    else:
        status='모델 데이터를 내려받아 파일을 준비하고 있습니다.'
    return {'fraction':min(1,max(0,event['received']/max(event['total'],1))),
            'status':status,
            'elapsed':duration(now-event['started']),
            'eta':duration(eta),
            'size':f"{event['received']/1024**2:,.1f} / {event['total']/1024**2:,.1f} MB",
            'speed':'측정 대기' if now-event['transfer_updated']>10 or not event['speed'] else f"{event['speed']/1024**2:,.2f} MB/s"}
