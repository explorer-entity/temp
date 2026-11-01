"""API test suite: python tests/test_api.py  (uses a throw-away database, never your smriti.db)"""
import os, sys, tempfile
os.environ["MANOVA_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as A, json, queue
FAILED = []
from datetime import datetime, timedelta, timezone
c=A.app.test_client()
H=lambda t:{"Authorization":"Bearer "+t}
def P(path,tok=None,**j): return c.post(path,json=j,headers=H(tok) if tok else {})
def G(path,tok=None): return c.get(path,headers=H(tok) if tok else {})
def ok(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond: FAILED.append(name)
ok("unauth read -> 401", G("/api/alerts/1").status_code==401)
pr=P("/api/register_patient",name="<b>Ama</b>",age=78,stage="Moderate").get_json(); pt,pid=pr["token"],pr["user_id"]
ok("patient gets token+pin", len(pr["pin"])==4 and pt)
cr=P("/api/register_caregiver",username="Ravi_k",password="secret1",name="Ravi").get_json(); ct,cid=cr["token"],cr["user_id"]
ok("weak password rejected", P("/api/register_caregiver",username="x1y2z",password="abc").status_code==400)
ok("dup username 409", P("/api/register_caregiver",username="ravi_k",password="secret1").status_code==409)
ok("caregiver blocked before link", G(f"/api/alerts/{pid}",ct).status_code==403)
ok("raw-ID link disabled", P("/api/link_caregiver",ct,caregiver_id=cid,patient_id=pid).status_code==403)
ok("bad code 404", P("/api/link_with_code",ct,code="000000").status_code==404)
code=P("/api/link_code",pt).get_json()["code"]
ok("caregiver cannot make link code", P("/api/link_code",ct).status_code==403)
r=P("/api/link_with_code",ct,code=code); ok("link with code", r.status_code==200 and r.get_json()["patient_id"]==pid)
ok("code is one-time", P("/api/link_with_code",ct,code=code).status_code==404)
ok("caregiver reads alerts after link", G(f"/api/alerts/{pid}",ct).status_code==200)
c2=P("/api/register_caregiver",username="other_cg",password="secret2").get_json()["token"]
ok("other caregiver blocked", G(f"/api/alerts/{pid}",c2).status_code==403)
ok("patient cannot act as another patient", P("/api/save_score",pt,user_id=pid+99,game_type="g",score=1).status_code==403)
ok("patient cannot set zones", P("/api/set_geofence_v2",pt,patient_id=pid,name="H",center_lat=26.1,center_lng=91.7,radius_meters=100).status_code==403)
ok("no consent -> 403", P("/api/update_location",pt,user_id=pid,latitude=26.1,longitude=91.7).status_code==403)
P("/api/consent",pt,allowed=True)
ok("zone by caregiver", P("/api/set_geofence_v2",ct,patient_id=pid,name="Home",center_lat=26.1,center_lng=91.7,radius_meters=100).status_code==200)
q=queue.Queue(); A._subscribers.setdefault(cid,set()).add(q)
ok("ping w/ consent", P("/api/update_location",pt,user_id=pid,latitude=26.1,longitude=91.7).status_code==200)
for _ in range(3): P("/api/update_location",pt,user_id=pid,latitude=26.2,longitude=91.8)
al=G(f"/api/alerts/{pid}",ct).get_json(); ok("one alert w/ id", len(al)==1 and "id" in al[0])
msg=json.loads(q.get_nowait()); ok("SSE push delivered", msg["patient_id"]==pid and msg["type"].startswith("Left Safe Zone"))
P("/api/trigger_alert",pt,user_id=pid,type="Lost My Way"); ok("SOS pushed", json.loads(q.get_nowait())["type"]=="Lost My Way")
ack=P(f"/api/alerts/{al[0]['id']}/acknowledge",ct,resolution="false_alarm").get_json(); ok("ack", ack["updated"]==1)
ok("patient cannot ack", P(f"/api/alerts/{al[0]['id']}/acknowledge",pt).status_code==403)
m=G(f"/api/metrics/{pid}",ct).get_json(); ok("metrics", m["alerts_total"]==2 and m["false_alarms"]==1 and m["median_response_seconds"] is not None)
old=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
P("/api/update_location",pt,user_id=pid,latitude=26.1,longitude=91.7,recorded_at=old)
hist=G(f"/api/location_history/{pid}?limit=100",ct).get_json(); ok("offline recorded_at honoured", any(h["timestamp"][:13]==old[:10]+" "+old[11:13] for h in hist))
future=(datetime.now(timezone.utc)+timedelta(days=2)).isoformat()
ok("future recorded_at ignored", P("/api/update_location",pt,user_id=pid,latitude=26.1,longitude=91.7,recorded_at=future).status_code==200)
log=G("/api/access_log",pt).get_json(); ok("patient sees audit log", any("location" in l["action"] for l in log) and any(l["caregiver"]=="Ravi" for l in log))
ok("my_caregivers", len(G("/api/my_caregivers",pt).get_json())==1)
# clinical
for s in [90,90,90,90]: P("/api/save_score",pt,user_id=pid,game_type="story_detective",score=s,max_score=100,difficulty="Easy")
for d,s in [("2026-09-01",26),("2026-10-01",22),("2026-10-30",18)]: P("/api/moca",ct,patient_id=pid,score=s,date=d)
ok("bad MoCA rejected", P("/api/moca",ct,patient_id=pid,score=31).status_code==400)
cl=G(f"/api/clinical/{pid}",ct).get_json(); ok("clinical json", cl["sessions"]==4 and len(cl["moca"])==3 and cl["weekly"])
rep=G(f"/api/report/{pid}?token={ct}"); html=rep.get_data(as_text=True)
ok("report html + token via query + escaped name", rep.status_code==200 and "&lt;b&gt;Ama" in html and "<b>Ama" not in html)
ok("report blocked for unlinked", G(f"/api/report/{pid}",c2).status_code==403)
# login
ok("patient login", P("/api/login",user_id=pid,secret=pr["pin"]).status_code==200)
ok("caregiver login", P("/api/login",username="RAVI_K",secret="secret1").status_code==200)
ok("wrong pw 401", P("/api/login",username="ravi_k",secret="nope").status_code==401)
codes=[P("/api/login",username="ravi_k",secret="bad").status_code for _ in range(10)]; ok("login rate limited", 429 in codes)
# revoke consent + unlink + erase
P("/api/consent",pt,allowed=False); ok("revoked consent stops ingestion", P("/api/update_location",pt,user_id=pid,latitude=26.1,longitude=91.7).status_code==403)
P("/api/unlink_caregiver",pt,caregiver_id=cid); ok("unlink revokes access", G(f"/api/alerts/{pid}",ct).status_code==403)
er=P("/api/erase_my_data",pt,scope="locations").get_json(); ok("erase locations", er["deleted"]["locations"]>=4)
er=P("/api/erase_my_data",pt,scope="all").get_json(); ok("erase all", "GameSessions" in er["deleted"])
ok("token dead after erase", G("/api/access_log",pt).status_code==401)
# static pages still open
ok("static open", c.get("/static/home.html").status_code==200 and c.get("/sw.js").status_code==200)

print("\n%d failed" % len(FAILED) if FAILED else "\nall checks passed")
sys.exit(1 if FAILED else 0)
