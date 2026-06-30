"""Discovery Agent (Phase 4).

Finds real openings in an open-ended order: public ATS JSON APIs
(Greenhouse/Lever/Ashby), then YC ``hiring.json`` + Hacker News, then company
career pages (Career Page Finder + ATS Detector), then a provider-abstracted web
search layer (Exa + Google CSE with failover). Job boards only within their ToS.
"""
