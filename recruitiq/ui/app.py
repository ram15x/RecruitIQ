import datetime as dt
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# streamlit puts this file's folder on the path, not the project root, so add it before importing the package
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

if os.environ.get("RECRUITIQ_EMBED") == "1":
    from recruitiq.ui.embed import start_api  # noqa: E402
    start_api()

from recruitiq.config import get_settings  # noqa: E402
from recruitiq.ui.client import Api, ApiError  # noqa: E402

st.set_page_config(page_title="RecruitIQ", layout="wide")
STATUS_ICON = {"evidenced": "shown in work history", "listed": "listed only", "related": "related skill", "missing": "not found"}


def api() -> Api:
    if "api" not in st.session_state:
        st.session_state.api = Api(get_settings().api_url)
    return st.session_state.api


def caps() -> dict:
    if "caps" not in st.session_state:
        st.session_state.caps = run(api().caps) or {}
    return st.session_state.caps


def run(fn, *a, **kw):
    # every call goes through here so an API error shows as a message instead of a stack trace
    try:
        return fn(*a, **kw)
    except ApiError as e:
        if e.status == 401 and "me" in st.session_state:
            st.session_state.pop("me")
            st.session_state.pop("api", None)
            st.rerun()
        st.error(e.message())
    except Exception:
        st.error("Could not reach the API. Is the server running?")
    return None


def demo_on() -> bool:
    try:
        return bool(api().health().get("demo"))
    except Exception:
        return False


def login_screen():
    st.title("RecruitIQ")
    st.caption("Resume screening where a person makes every decision")
    if demo_on():
        st.info("This is a demo with made-up candidates. "
                "Please do not upload real resumes here. The data resets when the server restarts.")
        if os.environ.get("RECRUITIQ_DEMO_HINT"):
            st.success(os.environ["RECRUITIQ_DEMO_HINT"])
    with st.form("login"):
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.form_submit_button("Sign in"):
            try:
                api().login(u, p)
                st.session_state.me = api().me()
                st.rerun()
            except ApiError as e:
                st.error("Could not sign in: " + e.message())
            except Exception:
                st.error("Could not reach the API. Is the server running?")


def _queue_section(title, key, items, hint):
    if not items:
        return
    with st.expander(f"{title} ({len(items)})", expanded=key in ("flagged", "final_decision")):
        st.caption(hint)
        st.dataframe(pd.DataFrame([{"ref": i["candidate_ref"], "job": i["job_title"], "score": i.get("score")} for i in items]), hide_index=True, width="stretch")


def _bulk_panel(items, decision, label):
    """One reason, one count, one click. Rejection emails go out only here, never on their own."""
    if not items:
        return
    ids = [i["id"] for i in items]
    st.markdown(f"**{label}** for the {len(ids)} listed above")
    reason = st.text_input("One reason for all of them (required, at least 10 characters)", key=f"br_{decision}")
    count = st.number_input("Type the number of people this will affect", 0, 10000, 0, key=f"bc_{decision}")
    send = st.checkbox("Also send each person the standard email", key=f"bs_{decision}")
    invite = decision == "shortlist" and st.checkbox("Also invite them to the interview", key=f"bi_{decision}")
    if st.button(label, key=f"bb_{decision}", disabled=len(reason.strip()) < 10 or count != len(ids)):
        r = run(api().bulk_decision, {"application_ids": ids, "decision": decision, "reason": reason, "confirm_count": int(count), "send": send, "invite": invite})
        if r:
            st.success(f"Done for {r['decided']}. Skipped {r['skipped_not_pending']} that were not waiting any more. Mail: {r['mail']}")
            st.rerun()


def page_overview():
    t = run(api().todo)
    if not t:
        return
    n = t["counts"]
    waiting = sum(n.values())
    if waiting == 0:
        st.success("Nothing needs you right now. Applications are being handled by the rules you set for each job.")
    else:
        st.subheader(f"{waiting} things need a person")
    if not t["mail_ready"]:
        st.warning("Email is not set up, so nothing is being sent automatically. Messages wait as drafts.")
    it = t["items"]
    _queue_section("Flagged for a closer look", "flagged", it["flagged"], "Something odd in the file (hidden text, text aimed at an AI, copied job description). Open each one and read it yourself.")
    _queue_section("Interviews finished, waiting for your decision", "final_decision", it["final_decision"], "The answers and the review are ready. Accept or reject from the Candidates page.")
    _queue_section("Borderline", "borderline", it["borderline"], "Scores between the two lines you set. Read these.")
    _queue_section("Suggested: shortlist", "suggested_acceptances", it["suggested_acceptances"], "Strong matches with no flags. Nothing has been sent to them.")
    _bulk_panel(it["suggested_acceptances"], "shortlist", "Shortlist all")
    _queue_section("Suggested: reject", "suggested_rejections", it["suggested_rejections"], "Low scores. Nothing has been sent. Look at a few before you confirm.")
    _bulk_panel(it["suggested_rejections"], "reject", "Reject all")
    if it["mail_waiting"]:
        with st.expander(f"Emails waiting or failed ({len(it['mail_waiting'])})"):
            st.dataframe(pd.DataFrame(it["mail_waiting"]), hide_index=True, width="stretch")
    d = run(api().dashboard)
    if d:
        st.divider()
        c = st.columns(3)
        c[0].metric("Open jobs", d["open_jobs"])
        c[1].metric("Applications", sum(d["by_status"].values()))
        c[2].metric("Flagged", d["flagged_for_review"])
        if d["by_status"]:
            st.bar_chart(pd.Series(d["by_status"], name="applications"))


def page_jobs():
    st.subheader("New job")
    if caps().get("llm"):
        with st.expander("Research a current market job description (web search)"):
            rt = st.text_input("Role", placeholder="Backend Engineer", key="rtitle")
            rl = st.text_input("Location (optional)", key="rloc")
            if st.button("Research it") and rt:
                with st.spinner("Searching current postings..."):
                    r = run(api().research, rt, rl)
                if r:
                    st.session_state.researched = r
                    st.session_state["jtitle"] = rt
                    st.session_state["jdesc"] = r["description"]
                    st.rerun()
        if st.session_state.get("researched"):
            rr = st.session_state["researched"]
            st.info(rr["note"])
            for src in rr["sources"]:
                st.markdown(f"- [{src['title']}]({src['url']})")
    with st.form("job"):
        title = st.text_input("Title", key="jtitle")
        desc = st.text_area("Description", height=200, key="jdesc", help="Put must-haves and nice-to-haves under separate headings so they can be told apart.")
        years = st.number_input("Minimum years (0 = take it from the text)", 0.0, 40.0, 0.0, 0.5)
        preview = st.form_submit_button("Preview extracted skills")
    if preview and title and desc:
        r = run(api().parse_job, {"title": title, "description": desc, "min_years": years or None})
        if r:
            st.session_state.parsed = r
    if "parsed" in st.session_state:
        p = st.session_state.parsed
        st.write("Check these before saving. Edit them if the text missed something.")
        if p.get("llm_suggestion"):
            sg = p["llm_suggestion"]
            st.caption("A language model also read the job text. Required: " + (", ".join(sg["required"]) or "none") + ". Preferred: " + (", ".join(sg["preferred"]) or "none") + ".")
        req = st.text_input("Required skills (comma separated)", ", ".join(p["required"]))
        pref = st.text_input("Preferred skills (comma separated)", ", ".join(p["preferred"]))
        if st.button("Save job"):
            body = {"title": title, "description": desc, "required": [s.strip() for s in req.split(",") if s.strip()],
                    "preferred": [s.strip() for s in pref.split(",") if s.strip()], "min_years": years or p["min_years"]}
            if run(api().add_job, body):
                st.session_state.pop("parsed")
                st.success("Job saved.")
                st.rerun()
    st.subheader("Jobs")
    for j in run(api().jobs) or []:
        with st.expander(f"{j['title']}  ({j['status']})"):
            st.write("Required: " + (", ".join(j["required"]) or "none"))
            st.write("Preferred: " + (", ".join(j["preferred"]) or "none"))
            st.write(f"Minimum years: {j['min_years'] if j['min_years'] is not None else 'not set'}")
            ap = j.get("autopilot") or {}
            if j["status"] == "open":
                st.markdown("**Autopilot for this job**")
                a1 = st.checkbox("Email each applicant to say it was received", bool(ap.get("acknowledge")), key=f"ak{j['id']}")
                on = st.checkbox("Invite strong, unflagged matches automatically", ap.get("auto_invite_min") is not None, key=f"ai{j['id']}")
                inv = st.slider("Invite at or above", 50, 100, int(ap.get("auto_invite_min") or 80), key=f"am{j['id']}", disabled=not on)
                mode = st.selectbox("Interview format", ["written", "voice"], ["written", "voice"].index(ap.get("interview_mode", "written")), key=f"im{j['id']}")
                lo = st.slider("Suggest rejecting below", 0, 70, int(ap.get("suggest_reject_below", 40)), key=f"lo{j['id']}")
                hi = st.slider("Suggest shortlisting from", 50, 100, int(ap.get("suggest_accept_from", 70)), key=f"hi{j['id']}")
                st.caption("Rejections are never sent automatically. They wait for you on the Overview page.")
                if st.button("Save autopilot", key=f"sv{j['id']}"):
                    r = run(api().set_autopilot, j["id"], {"acknowledge": a1, "auto_invite_min": float(inv) if on else None, "interview_mode": mode,
                                                           "suggest_reject_below": float(lo), "suggest_accept_from": float(hi)})
                    if r:
                        st.success("Saved")
            if j["status"] == "open" and st.button("Close this job", key=f"close{j['id']}"):
                run(api().close_job, j["id"])
                st.rerun()


def pick_job(key="job"):
    jobs = run(api().jobs) or []
    if not jobs:
        st.info("Create a job first.")
        return None
    return st.selectbox("Job", jobs, format_func=lambda j: f"{j['title']} ({j['status']})", key=key)


def page_candidates():
    job = pick_job()
    if not job:
        return
    with st.expander("Add an application"):
        with st.form("apply"):
            name = st.text_input("Candidate name")
            email = st.text_input("Candidate email")
            f = st.file_uploader("Resume (PDF, DOCX or TXT)", type=["pdf", "docx", "txt"])
            consent = st.checkbox("The candidate has agreed to us processing this application")
            if st.form_submit_button("Score it"):
                if not (name and email and f):
                    st.error("Name, email and a file are all needed.")
                else:
                    r = run(api().apply_file, job["id"], name, email, consent, f.name, f.getvalue())
                    if r:
                        st.success(f"Scored {r['score']} ({r['band']}).")
    rows = run(api().ranked, job["id"]) or []
    if not rows:
        st.write("No applications yet.")
        return
    st.caption("Names are hidden on purpose. Open an application to read the evidence first.")
    df = pd.DataFrame([{"id": r["id"], "ref": r["candidate_ref"], "score": r["score"], "band": r["band"], "status": r["status"],
                        "closer look": "yes" if r["needs_review"] else "", "flags": r["flags"]} for r in rows])
    st.dataframe(df, hide_index=True, width="stretch")
    xl = run(api().export, job["id"], False)
    if xl:
        st.download_button("Download this list as Excel", xl, file_name=f"recruitiq_job_{job['id']}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    pool_search(job["id"])
    pool_ask(job["id"])
    compare_box(job["id"], rows)
    aid = st.selectbox("Open application", [r["id"] for r in rows], format_func=lambda i: next(r["candidate_ref"] for r in rows if r["id"] == i))
    detail(aid)


def pool_search(jid):
    with st.expander("Search the resumes", expanded=False):
        st.caption("Returns lines straight from the resumes. Nothing is summarised, so what you see is what they wrote.")
        q = st.text_input("A skill or a phrase", placeholder="kafka, led a team, on-call", key=f"q{jid}")
        if q and len(q.strip()) >= 2:
            r = run(api().search, jid, q)
            if r:
                st.write(f"{len(r['matches'])} of {r['searched']} resumes match.")
                for m in r["matches"]:
                    st.markdown(f"**{m['candidate_ref']}**, score {m['score']}")
                    for ln in m["lines"]:
                        tag = " (only in a skills list)" if ln["only_in_skills_list"] else ""
                        st.markdown(f"> {ln['text']}{tag}")


def pool_ask(jid):
    if not caps().get("llm"):
        return
    with st.expander("Ask a question about the resumes (language model)"):
        st.caption("Only anonymised lines from the resumes are sent. The answer has to cite them, and resumes that contain text aimed at AI systems are left out.")
        q = st.text_input("Question", placeholder="Who has run production systems on Kubernetes?", key=f"ask{jid}")
        if st.button("Ask", key=f"askb{jid}") and q:
            r = run(api().ask, jid, q)
            if r:
                st.write(r["answer"])
                for src in r["sources"]:
                    st.markdown(f"> {src['ref']}: {src['text']}")
                if r.get("resumes_left_out"):
                    st.info(f"{r['resumes_left_out']} resume(s) were left out because they contain instructions aimed at AI systems.")


def compare_box(jid, rows):
    with st.expander("Compare two candidates"):
        ids = [r["id"] for r in rows]
        if len(ids) < 2:
            st.write("Needs two applications.")
            return
        ref = {r["id"]: r["candidate_ref"] for r in rows}
        c1, c2 = st.columns(2)
        x = c1.selectbox("First", ids, format_func=ref.get, key=f"cx{jid}")
        y = c2.selectbox("Second", ids, index=1, format_func=ref.get, key=f"cy{jid}")
        if x != y:
            r = run(api().compare, jid, x, y)
            if r:
                df = pd.DataFrame([{"skill": s["skill"], "type": s["kind"], r["a"]: s["a"], r["b"]: s["b"]} for s in r["skills"]])
                st.dataframe(df, hide_index=True, width="stretch")
                comp = pd.DataFrame({r["a"]: {k: v["a"] for k, v in r["components"].items()}, r["b"]: {k: v["b"] for k, v in r["components"].items()}})
                st.bar_chart(comp.fillna(0))


def detail(aid):
    reveal = st.toggle("Show name and email (this is logged)", key=f"rev{aid}")
    a = run(api().application, aid, reveal)
    if not a:
        return
    res = a["result"]
    st.markdown(f"### {a['candidate_ref']}: {a['score']} ({a['band']})")
    if reveal:
        st.write(f"**{a['identity']['name']}**, {a['identity']['email']}")
    for f in res.get("flags", []):
        st.warning(f"{f['kind']}: {f['detail']}")
    for n in res.get("notes", []):
        st.info(n)
    w = res["weights"]
    st.write("How the score was made: " + ", ".join(f"{k} {w[k]:.0%}" for k in w))
    comp = {k: v for k, v in res["components"].items() if v is not None}
    st.bar_chart(pd.Series(comp, name="component score (0 to 1)"))
    for title, key in (("Required skills", "required"), ("Preferred skills", "preferred")):
        if res.get(key):
            st.markdown(f"**{title}**")
            for r in res[key]:
                line = f"- {r['skill']}: {STATUS_ICON[r['status']]}"
                if r["status"] == "related":
                    line += f" (from {r['via']})"
                if r.get("evidence"):
                    line += f"\n  > {r['evidence']}"
                st.markdown(line)
    if a.get("gaps"):
        st.markdown("**What is holding the score back** (exact, from the weights above)")
        for g in a["gaps"][:5]:
            st.markdown(f"- {g['skill']} ({g['status']}): up to +{g['gain']} points if shown in the work history")
    if caps().get("llm") and st.button("Write a reviewer brief (language model)", key=f"brief{aid}"):
        b = run(api().brief, aid)
        if b and b.get("blocked"):
            st.warning(b["blocked"])
        elif b:
            st.caption(b["note"])
            for title, key in (("Strengths", "strengths"), ("Gaps", "gaps")):
                if b[key]:
                    st.markdown(f"**{title}**")
                    for p_ in b[key]:
                        st.markdown(f"- {p_['point']}" + (f"\n  > {p_['quote']}" if p_["quote"] else ""))
            if b["questions"]:
                st.markdown("**Questions to ask**")
                for q in b["questions"]:
                    st.markdown(f"- {q}")
    with st.expander("Exactly what the scorer read (identity removed)"):
        st.text(a["what_the_scorer_saw"])
    st.markdown("**Your decision**")
    if a["decision_reason"]:
        st.write(f"Current: {a['status']}. Reason: {a['decision_reason']}")
    reason = st.text_area("Your reason (required, at least 10 characters). Say what you saw in the resume.", key=f"reason{aid}")
    tabs = st.tabs(["Accept", "Reject", "Hold"])
    for tab, dec, label in ((tabs[0], "shortlist", "Accept"), (tabs[1], "reject", "Reject")):
        with tab:
            pv = run(api().preview, aid, dec)
            if not pv:
                continue
            st.caption(f"This email goes to the candidate when you press the button. Edit it first if you want. To: {pv['to'] if reveal else 'the candidate'}")
            subj = st.text_input("Subject", pv["subject"], key=f"sub{dec}{aid}")
            msg = st.text_area("Message", pv["body"], height=220, key=f"msg{dec}{aid}")
            if st.button(f"{label} and send the email", key=f"go{dec}{aid}", type="primary" if dec == "shortlist" else "secondary"):
                r = run(api().decide, aid, dec, reason, True, subj, msg)
                if r:
                    m = r.get("mail", {})
                    if m.get("status") == "sent":
                        st.success("Recorded, and the email was sent.")
                    else:
                        st.warning("Recorded. The email was NOT sent: " + (m.get("error") or "unknown") + ". It is saved as a draft.")
    with tabs[2]:
        if st.button("Put on hold (no email)", key=f"hold{aid}") and run(api().decide, aid, "hold", reason):
            st.rerun()
    c = st.columns(3)
    pdf = run(api().report, aid, reveal)
    if pdf:
        c[0].download_button("Download review PDF", pdf, file_name=f"review_{a['candidate_ref']}.pdf", mime="application/pdf")
    if a["status"] in ("shortlisted", "rejected") and c[1].button("Draft the email", key=f"mail{aid}"):
        st.session_state[f"draft{aid}"] = run(api().draft_mail, aid)
    if (dr := st.session_state.get(f"draft{aid}")):
        st.text_input("To", dr["to"], disabled=True)
        st.text_input("Subject", dr["subject"], disabled=True)
        st.text_area("Body", dr["body"], height=200, disabled=True)
        if st.button("Send this email", key=f"send{aid}"):
            r = run(api().send_mail, dr["id"])
            if r:
                st.success("Sent.") if r["status"] == "sent" else st.error("Not sent: " + r["error"])
    if a["status"] in ("shortlisted", "interview_invited"):
        with st.form(f"iv{aid}"):
            st.markdown("**Schedule an interview**")
            day = st.date_input("Date", dt.date.today() + dt.timedelta(days=2))
            tm = st.time_input("Time (UTC)", dt.time(10, 0))
            mins = st.number_input("Minutes allowed", 10, 180, 45)
            mode = st.radio("Format", ["written", "voice"], horizontal=True, format_func=lambda m: "Typed answers" if m == "written" else "Voice: questions read aloud, spoken answers (typing always allowed)")
            video = st.checkbox("Also record video (voice format only). The candidate is told and has to agree.", value=False)
            if st.form_submit_button("Create the interview link"):
                when = dt.datetime.combine(day, tm, tzinfo=dt.timezone.utc).isoformat()
                r = run(api().schedule, aid, {"scheduled_at": when, "duration_minutes": int(mins), "mode": mode, "record_video": bool(video and mode == "voice")})
                if r:
                    st.success("Link created. The invitation is a draft until you send it.")
                    st.code(r["link"])
    for i in a["interviews"]:
        if i["status"] != "completed":
            continue
        with st.expander(f"Interview {i['id']}: {i['status']} ({i['mode']})"):
            qa = {str(q["id"]): q for q in i["questions"]}
            if not reveal:
                st.caption("Turn on \"Show name and email\" above to read the answers and play recordings. This is logged.")
            else:
                for qid, q in qa.items():
                    st.markdown(f"**{q['id']}. {q['text']}**")
                    st.write((i["answers"] or {}).get(qid) or "_no answer_")
                if i["mode"] == "voice":
                    st.caption("Recordings are for a person to watch and listen to. Nothing analyses voice or face.")
                    have = {m["question_id"]: m for m in run(api().media_list, aid, i["id"]) or []}
                    for qid in qa:
                        m = have.get(int(qid))
                        if m and st.button(f"Load the recording for question {qid}", key=f"m{i['id']}_{qid}"):
                            data = run(api().media, aid, i["id"], int(qid))
                            if data:
                                (st.video if m["kind"] == "video" else st.audio)(data, format=m["mime"])
            st.markdown("**Facts about the answers**")
            st.json(i["analysis"].get("answers", []))
            st.json(i["analysis"].get("signals", {}))
            if caps().get("llm"):
                if st.button("Have a language model read the answers (text only)", key=f"rv{i['id']}"):
                    r = run(api().review, aid, i["id"])
                    if r and r.get("blocked"):
                        st.warning(r["blocked"])
                    elif r:
                        st.caption(r["note"])
                        for v in r["reviews"]:
                            st.markdown(f"Q{v['question_id']}: relevance **{v['relevance']}**, specificity **{v['specificity']}**, reasoning **{v['reasoning']}**. {v['explanation']}" + (f"\n> {v['quote']}" if v["quote"] else ""))
                mr = i["analysis"].get("model_review")
                if mr and not st.session_state.get(f"shown{i['id']}"):
                    st.caption("Saved review: " + mr["note"])
                    for v in mr["reviews"]:
                        st.markdown(f"Q{v['question_id']}: relevance **{v['relevance']}**, specificity **{v['specificity']}**, reasoning **{v['reasoning']}**. {v['explanation']}")
    with st.expander("Voluntary self-reported group (used only for the fairness report)"):
        g = st.text_input("Group label", key=f"grp{aid}")
        if st.button("Save", key=f"grps{aid}") and g:
            run(api().set_group, aid, g)
            st.success("Saved.")


def page_fairness():
    job = pick_job("fjob")
    if not job:
        return
    stage = st.radio("Look at", ["human", "model"], format_func=lambda s: "What people decided" if s == "human" else "What the score alone would pick (70+)", horizontal=True)
    mg = st.number_input("Smallest group size to judge", 2, 100, 10)
    r = run(api().fairness, job["id"], stage, int(mg))
    if not r:
        return
    st.caption(r["note"])
    for w in r.get("warnings", []):
        st.info(w)
    if r.get("groups"):
        df = pd.DataFrame(r["groups"]).T
        st.dataframe(df, width="stretch")
        if r["flagged"]:
            st.warning("Groups below four-fifths of the top rate: " + ", ".join(r["flagged"]))
        else:
            st.success("No group is flagged. That is not proof the process is fair.")


def page_admin():
    me = st.session_state.me
    if me["role"] != "admin":
        st.info("Admins only.")
        return
    st.subheader("Audit log")
    log = run(api().audit) or []
    if log:
        st.dataframe(pd.DataFrame(log), hide_index=True, width="stretch")
    st.subheader("Mailbox")
    if caps().get("inbox"):
        st.write("Reads unread mail, scores PDF and Word attachments, and marks those messages read. Put [job:ID] in the subject, or the job title. Nothing is sent or deleted.")
        if st.button("Pull applications from the mailbox now"):
            r = run(api().poll_inbox)
            if r is not None:
                st.success(f"{r['read']} read, {r['created']} added, {r['already_applied']} already applied.")
                for x in r["left_unread"]:
                    st.warning(f"Left unread: {x['from']} ({x['subject']}): {x['why']}")
    else:
        st.write("Not set up. Set IMAP_USER and IMAP_PASSWORD (a Gmail app password), or the SMTP ones, then restart.")
    st.subheader("Add a user")
    with st.form("user"):
        u = st.text_input("Username")
        p = st.text_input("Password (10+ characters)", type="password")
        role = st.selectbox("Role", ["recruiter", "admin"])
        if st.form_submit_button("Create") and run(api().add_user, {"username": u, "password": p, "role": role}):
            st.success("User created.")
    st.subheader("Data retention")
    if st.button("Delete candidates past their retention date"):
        r = run(api().purge)
        if r is not None:
            st.success(f"{r['removed']} removed.")
    cid = st.number_input("Erase one candidate by id (removes their applications and interviews)", 0, step=1)
    if st.button("Erase") and cid:
        if run(api().erase, int(cid)):
            st.success("Erased.")


if "me" not in st.session_state:
    login_screen()
else:
    me = st.session_state.me
    st.sidebar.write(f"{me['username']} ({me['role']}), {me['org_name']}")
    if demo_on():
        st.sidebar.warning("Demo data. No real resumes, please.")
    page = st.sidebar.radio("Go to", ["Overview", "Jobs", "Candidates", "Fairness", "Admin"])
    if st.sidebar.button("Sign out"):
        st.session_state.clear()
        st.rerun()
    {"Overview": page_overview, "Jobs": page_jobs, "Candidates": page_candidates, "Fairness": page_fairness, "Admin": page_admin}[page]()
