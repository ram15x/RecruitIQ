import httpx


class ApiError(Exception):
    def __init__(self, status, detail):
        self.status, self.detail = status, detail
        super().__init__(f"{status}: {detail}")

    def message(self):
        d = self.detail
        if isinstance(d, list):
            # pydantic validation errors come back as a list of dicts
            return "; ".join(f"{'.'.join(str(x) for x in e.get('loc', [])[1:])}: {e.get('msg', '')}" for e in d)
        return str(d)


class Api:
    # thin wrapper so the dashboard never builds urls or headers by hand
    def __init__(self, base_url, token=None, transport=None):
        self.http = httpx.Client(base_url=base_url, timeout=60, transport=transport)
        self.token = token

    def _req(self, method, path, **kw):
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        r = self.http.request(method, path, headers=headers, **kw)
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail", r.text)
            except ValueError:
                detail = r.text
            raise ApiError(r.status_code, detail)
        return r

    def login(self, username, password):
        self.token = self._req("POST", "/auth/login", data={"username": username, "password": password}).json()["access_token"]

    def me(self): return self._req("GET", "/me").json()
    def dashboard(self): return self._req("GET", "/dashboard").json()
    def jobs(self): return self._req("GET", "/jobs").json()
    def parse_job(self, body): return self._req("POST", "/jobs/parse", json=body).json()
    def add_job(self, body): return self._req("POST", "/jobs", json=body).json()
    def close_job(self, jid): return self._req("POST", f"/jobs/{jid}/close").json()
    def ranked(self, jid, **params): return self._req("GET", f"/jobs/{jid}/applications", params=params).json()
    def apply_text(self, jid, body): return self._req("POST", f"/jobs/{jid}/applications/json", json=body).json()

    def apply_file(self, jid, name, email, consent, filename, data):
        return self._req("POST", f"/jobs/{jid}/applications", data={"name": name, "email": email, "consent": str(consent).lower()},
                         files={"file": (filename, data)}).json()

    def health(self): return self.http.get("/health").json()
    def search(self, jid, q): return self._req("GET", f"/jobs/{jid}/search", params={"q": q}).json()
    def compare(self, jid, a, b): return self._req("GET", f"/jobs/{jid}/compare", params={"a": a, "b": b}).json()
    def export(self, jid, reveal=False): return self._req("GET", f"/jobs/{jid}/export.xlsx", params={"reveal": reveal}).content
    def research(self, title, location=""): return self._req("POST", "/jobs/research", json={"title": title, "location": location}).json()
    def caps(self): return self._req("GET", "/capabilities").json()
    def brief(self, aid): return self._req("POST", f"/applications/{aid}/brief").json()
    def ask(self, jid, q): return self._req("POST", f"/jobs/{jid}/ask", json={"question": q}).json()
    def poll_inbox(self): return self._req("POST", "/admin/inbox/poll").json()
    def application(self, aid, reveal=False): return self._req("GET", f"/applications/{aid}", params={"reveal": reveal}).json()
    def decide(self, aid, decision, reason, send=False, subject=None, message=None):
        return self._req("POST", f"/applications/{aid}/decision", json={"decision": decision, "reason": reason, "send": send, "subject": subject, "message": message}).json()

    def preview(self, aid, decision): return self._req("GET", f"/applications/{aid}/message-preview", params={"decision": decision}).json()
    def report(self, aid, reveal=False): return self._req("GET", f"/applications/{aid}/report.pdf", params={"reveal": reveal}).content
    def draft_mail(self, aid): return self._req("POST", f"/applications/{aid}/notifications", json={"kind": "decision"}).json()
    def send_mail(self, nid): return self._req("POST", f"/notifications/{nid}/send").json()
    def schedule(self, aid, body): return self._req("POST", f"/applications/{aid}/interviews", json=body).json()
    def set_group(self, aid, label): return self._req("PUT", f"/applications/{aid}/demographic", json={"group_label": label}).json()
    def fairness(self, jid, stage, min_group): return self._req("GET", f"/jobs/{jid}/fairness", params={"stage": stage, "min_group": min_group}).json()
    def erase(self, cid): return self._req("DELETE", f"/candidates/{cid}").json()
    def purge(self): return self._req("POST", "/admin/retention/purge").json()
    def audit(self): return self._req("GET", "/audit").json()
    def add_user(self, body): return self._req("POST", "/users", json=body).json()
