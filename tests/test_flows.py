from datetime import date, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.clock import shop_today
from tests.helpers import as_role, future, past, register, set_only_role

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF"


def test_register_login_refresh_and_logout(client: TestClient, db) -> None:
    _email, headers, body = register(client)
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert "profile.read" in me.json()["permissions"]
    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": body["refresh_token"]})
    assert refreshed.status_code == 200
    old = client.post("/api/v1/auth/refresh", json={"refresh_token": body["refresh_token"]})
    assert old.status_code == 401
    logout = client.post("/api/v1/auth/logout", json={"refresh_token": refreshed.json()["refresh_token"]})
    assert logout.status_code == 204
    again = client.post("/api/v1/auth/refresh", json={"refresh_token": refreshed.json()["refresh_token"]})
    assert again.status_code == 401


def test_anonymous_is_401_and_customer_cannot_create_products(client: TestClient, db) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401
    _email, headers = as_role(client, "customer")
    denied = client.post(
        "/api/v1/products",
        headers=headers,
        json={"name": "Sev", "sku": "SEV", "price": "10.00"},
    )
    assert denied.status_code == 403


def test_deactivated_user_cannot_refresh(client: TestClient, db) -> None:
    email, _headers, body = register(client)
    _admin_email, admin = as_role(client, "admin")
    listed = client.get("/api/v1/users", headers=admin)
    target = next(row for row in listed.json()["items"] if row["email"] == email)
    deactivated = client.post(f"/api/v1/users/{target['id']}/deactivate", headers=admin)
    assert deactivated.status_code == 200
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": body["refresh_token"]}).status_code == 401


def test_password_reset_revokes_refresh_tokens(client: TestClient, db) -> None:
    email, _headers, body = register(client)
    forgot = client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert forgot.status_code == 200
    token = forgot.json()["reset_token"]
    assert token
    reset = client.post("/api/v1/auth/reset-password", json={"token": token, "password": "new-password-1"})
    assert reset.status_code == 200
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": body["refresh_token"]}).status_code == 401
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "new-password-1"})
    assert login.status_code == 200


def test_catalog_publish_hides_drafts(client: TestClient, db) -> None:
    _email, admin = as_role(client, "admin")
    sku = f"SKU-{uuid4().hex[:8]}"
    name = f"Snack {uuid4().hex[:6]}"
    created = client.post(
        "/api/v1/products",
        headers=admin,
        json={"name": name, "sku": sku, "price": "80.00", "description": "Spicy snack"},
    )
    assert created.status_code == 201, created.text
    product_id = created.json()["id"]
    slug = created.json()["slug"]
    assert client.get(f"/api/v1/products/by-slug/{slug}").status_code == 404
    published = client.post(f"/api/v1/products/{product_id}/publish", headers=admin)
    assert published.status_code == 200
    assert client.get(f"/api/v1/products/by-slug/{slug}").status_code == 200
    archived = client.post(f"/api/v1/products/{product_id}/archive", headers=admin)
    assert archived.status_code == 200
    assert client.get(f"/api/v1/products/by-slug/{slug}").status_code == 404
    listed = client.get("/api/v1/products")
    assert all(item["id"] != product_id for item in listed.json()["items"])


def test_campaign_is_public_only_inside_its_window(client: TestClient, db) -> None:
    _email, admin = as_role(client, "admin")
    created = client.post(
        "/api/v1/campaigns",
        headers=admin,
        json={"name": "Diwali Special", "start_at": future(1), "end_at": future(5), "description": "Faral"},
    )
    assert created.status_code == 201, created.text
    campaign_id = created.json()["id"]
    slug = created.json()["slug"]
    preview = client.post(f"/api/v1/campaigns/{campaign_id}/preview", headers=admin)
    assert preview.status_code == 200
    assert preview.json()["preview"] is True
    assert client.get(f"/api/v1/campaigns/{slug}").status_code == 404
    updated = client.patch(
        f"/api/v1/campaigns/{campaign_id}",
        headers=admin,
        json={"start_at": past(1), "end_at": future(2)},
    )
    assert updated.status_code == 200
    client.post(f"/api/v1/campaigns/{campaign_id}/publish", headers=admin)
    public = client.get(f"/api/v1/campaigns/{slug}")
    assert public.status_code == 200
    assert public.json()["active"] is True


def test_guest_cart_merges_and_becomes_an_order(client: TestClient, db) -> None:
    _email, admin = as_role(client, "admin")
    product = client.post(
        "/api/v1/products",
        headers=admin,
        json={"name": "Chakli", "sku": f"CK-{uuid4().hex[:6]}", "price": "50.00", "description": "Crunchy"},
    )
    product_id = product.json()["id"]
    client.post(f"/api/v1/products/{product_id}/publish", headers=admin)
    guest = "guest-token-123456"
    added = client.post(
        "/api/v1/cart/items",
        headers={"X-Guest-Token": guest},
        json={"product_id": product_id, "quantity": 2},
    )
    assert added.status_code == 201, added.text
    email, _headers, _body = register(client)
    logged_in = client.post("/api/v1/auth/login", json={"email": email, "password": "password123", "guest_token": guest})
    assert logged_in.status_code == 200
    customer = {"Authorization": f"Bearer {logged_in.json()['access_token']}"}
    cart = client.get("/api/v1/cart", headers=customer)
    assert cart.json()["items"][0]["quantity"] == 2
    inquiry = client.post(
        "/api/v1/inquiries",
        headers={**customer, "X-Guest-Token": guest},
        json={"name": "Guest Shopper", "phone": "9999999999", "from_cart": True, "message": "Please pack"},
    )
    assert inquiry.status_code == 201, inquiry.text
    inquiry_id = inquiry.json()["id"]
    order = client.post(f"/api/v1/inquiries/{inquiry_id}/order", headers=admin)
    assert order.status_code == 201, order.text
    own = client.get(f"/api/v1/orders/{order.json()['id']}", headers=customer)
    assert own.status_code == 200
    other_email, other, _other_body = register(client)
    set_only_role(other_email, "customer")
    denied = client.get(f"/api/v1/orders/{order.json()['id']}", headers=other)
    assert denied.status_code == 403


def test_private_document_stays_hidden_until_publish(client: TestClient, db) -> None:
    _email, admin = as_role(client, "admin")
    created = client.post(
        "/api/v1/documents",
        headers=admin,
        data={"title": "FSSAI License", "category": "license"},
        files={"file": ("license.pdf", PDF, "application/pdf")},
    )
    assert created.status_code == 201, created.text
    document_id = created.json()["id"]
    assert client.get(f"/api/v1/documents/public/{document_id}/file").status_code == 404
    assert all(row["id"] != document_id for row in client.get("/api/v1/documents/public").json())
    client.post(f"/api/v1/documents/{document_id}/publish", headers=admin)
    public = client.get(f"/api/v1/documents/public/{document_id}/file")
    assert public.status_code == 200
    assert public.content.startswith(b"%PDF")
    rejected = client.post(
        "/api/v1/documents",
        headers=admin,
        data={"title": "Bad", "category": "license"},
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert rejected.status_code == 400


def test_partial_payment_updates_outstanding_and_hides_proof(client: TestClient, db) -> None:
    _email, admin = as_role(client, "admin")
    super_email, super_headers = as_role(client, "super_admin")
    partner = client.post("/api/v1/business-partners", headers=admin, json={"name": "Shree Mills", "roles": ["vendor"]})
    assert partner.status_code == 201, partner.text
    purchase = client.post(
        "/api/v1/purchases",
        headers=admin,
        json={
            "partner_id": partner.json()["id"],
            "purchased_on": shop_today().isoformat(),
            "items": [{"description": "Besan", "amount": "100.00"}],
        },
    )
    invoice = client.post(
        f"/api/v1/purchases/{purchase.json()['id']}/invoices",
        headers=admin,
        json={"invoice_number": f"INV-{uuid4().hex[:6]}", "amount": "100.00", "due_date": (shop_today() - timedelta(days=3)).isoformat()},
    )
    assert invoice.status_code == 201, invoice.text
    invoice_id = invoice.json()["id"]
    first = client.post(
        "/api/v1/payments",
        headers=admin,
        json={"invoice_id": invoice_id, "amount": "40.00", "paid_on": date.today().isoformat(), "method": "upi"},
    )
    assert first.status_code == 201, first.text
    assert first.json()["outstanding"] == "60.00"
    proof = client.post(
        f"/api/v1/payments/{first.json()['id']}/attachments",
        headers=admin,
        files={"file": ("proof.pdf", PDF, "application/pdf")},
    )
    assert proof.status_code == 201
    hidden = client.get(f"/api/v1/payments/{first.json()['id']}/attachments/{proof.json()['id']}", headers=admin)
    assert hidden.status_code == 403
    visible = client.get(
        f"/api/v1/payments/{first.json()['id']}/attachments/{proof.json()['id']}",
        headers=super_headers,
    )
    assert visible.status_code == 200
    assert super_email
    second = client.post(
        "/api/v1/payments",
        headers=admin,
        json={"invoice_id": invoice_id, "amount": "60.00", "paid_on": date.today().isoformat(), "method": "cash"},
    )
    assert second.json()["outstanding"] == "0.00"
    too_much = client.post(
        "/api/v1/payments",
        headers=admin,
        json={"invoice_id": invoice_id, "amount": "1.00", "paid_on": date.today().isoformat()},
    )
    assert too_much.status_code == 400


def test_reminder_suppression_for_overdue_invoice_and_expiring_document(client: TestClient, db) -> None:
    _email, admin = as_role(client, "admin")
    partner = client.post("/api/v1/business-partners", headers=admin, json={"name": "Oil Press", "roles": ["raw_material_supplier"]})
    purchase = client.post(
        "/api/v1/purchases",
        headers=admin,
        json={
            "partner_id": partner.json()["id"],
            "purchased_on": shop_today().isoformat(),
            "items": [{"description": "Oil", "amount": "20.00"}],
        },
    )
    client.post(
        f"/api/v1/purchases/{purchase.json()['id']}/invoices",
        headers=admin,
        json={
            "invoice_number": f"INV-{uuid4().hex[:6]}",
            "amount": "20.00",
            "due_date": (shop_today() - timedelta(days=2)).isoformat(),
        },
    )
    client.post(
        "/api/v1/documents",
        headers=admin,
        data={"title": "GST", "category": "tax", "expiry_date": (shop_today() + timedelta(days=2)).isoformat()},
        files={"file": ("gst.pdf", PDF, "application/pdf")},
    )
    first = client.post("/api/v1/reminders/run", headers=admin)
    second = client.post("/api/v1/reminders/run", headers=admin)
    assert first.status_code == 200, first.text
    assert first.json()["created"] >= 2
    assert second.json()["created"] == 0


def test_audit_and_dashboard(client: TestClient, db) -> None:
    _email, admin = as_role(client, "admin")
    _super_email, super_headers = as_role(client, "super_admin")
    product = client.post(
        "/api/v1/products",
        headers=admin,
        json={"name": "Gathiya", "sku": f"GA-{uuid4().hex[:6]}", "price": "30.00"},
    )
    client.post(f"/api/v1/products/{product.json()['id']}/publish", headers=admin)
    denied = client.get("/api/v1/audit-logs", headers=admin)
    assert denied.status_code == 403
    logs = client.get("/api/v1/audit-logs", headers=super_headers)
    assert logs.status_code == 200
    actions = {row["action"] for row in logs.json()["items"]}
    assert "product.publish" in actions
    dashboard = client.get("/api/v1/admin/dashboard", headers=admin)
    assert dashboard.status_code == 200
    assert dashboard.json()["published_products"] >= 1
    updated = client.patch("/api/v1/settings/shop_name", headers=super_headers, json={"value": "Mahavir Farsan Mart"})
    assert updated.status_code == 200
    assert client.patch("/api/v1/settings/shop_name", headers=admin, json={"value": "no"}).status_code == 403


def test_homepage_renders_published_sections(client: TestClient, db) -> None:
    _email, admin = as_role(client, "admin")
    slug = f"home-{uuid4().hex[:8]}"
    page = client.post("/api/v1/admin/pages", headers=admin, json={"title": "Festival", "slug": slug})
    assert page.status_code == 201, page.text
    page_id = page.json()["id"]
    section = client.post(
        "/api/v1/admin/page-sections",
        headers=admin,
        json={"page_id": page_id, "type": "hero", "title": "Welcome", "subtitle": "Fresh farsan", "sort_order": 1},
    )
    assert section.status_code == 201, section.text
    assert client.get(f"/api/v1/pages/{slug}").status_code == 404
    published = client.post(f"/api/v1/admin/pages/{page_id}/publish", headers=admin)
    assert published.status_code == 200
    home = client.get(f"/api/v1/pages/{slug}")
    assert home.status_code == 200
    assert home.json()["sections"][0]["title"] == "Welcome"
