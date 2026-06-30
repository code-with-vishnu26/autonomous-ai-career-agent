"""External integrations: Gmail connector and the supervised browser.

The browser (Playwright + Browser-Use) is driven only under human supervision,
reusing a session from a manual login. Gmail is used for email-to-apply and,
later, reading responses. The agent never automates Google OAuth itself.
"""
