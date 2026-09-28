"""Seed demo data: org "acme", an admin, a reviewer, one account placeholder.

Run: python -m backend.store.seed_demo   (idempotent)
"""

from sqlalchemy.orm import Session

from backend.store import repo
from backend.store.db import SessionLocal, init_db
from backend.store.models import Account, Org, Role, User

ORG_ID = "acme"


def seed(s: Session) -> Org:
    org = s.get(Org, ORG_ID)
    if org:
        return org
    org = repo.create_org(s, "Acme", org_id=ORG_ID)
    s.add_all([
        User(id="u-admin", org_id=org.id, name="Ada Admin", email="admin@acme.test", role=Role.admin),
        User(id="u-reviewer", org_id=org.id, name="Riley Reviewer", email="reviewer@acme.test",
             slack_id="U00REVIEW", role=Role.reviewer),
    ])
    s.add(Account(id="acct-sandbox", org_id=org.id, alias="sandbox", aws_account_id="000000000000",
                  role_arn="local", external_id="demo-external-id", regions=["us-east-1"]))
    s.commit()
    return org


if __name__ == "__main__":
    init_db()
    with SessionLocal() as session:
        print("seeded org:", seed(session).id)
