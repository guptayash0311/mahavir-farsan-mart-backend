"""Local sample data for every application that already has tables.

Run from the backend directory after migrations:

    python -m scripts.seed

The Super Admin comes from BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD.
That password is never printed. Staff and customer sample accounts share
SAMPLE_PASSWORD, which is local only.
"""

import base64
import sys
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.clock import shop_today, utc_now
from app.core.config import get_settings
from app.core.database import get_engine
from app.core.money import money
from app.core.security import hash_password
from app.core.slug import unique_slug
from app.core.storage import get_storage
from app.modules.automation.models import Reminder, ReminderRule
from app.modules.automation.service import ensure_default_rules
from app.modules.business.models import Address, BusinessPartner, Contact, Invoice, PartnerRole, Payment, Purchase, PurchaseItem
from app.modules.catalog.models import (
    Brand,
    Category,
    Manufacturer,
    Product,
    ProductAttribute,
    ProductCategory,
    ProductMedia,
)
from app.modules.cms.models import Campaign, CampaignProduct, Page, PageSection
from app.modules.commerce.models import (
    Cart,
    CartItem,
    CustomerProfile,
    Inquiry,
    InquiryItem,
    Order,
    OrderItem,
    Wishlist,
    WishlistItem,
)
from app.modules.documents.models import Document, DocumentVersion
from app.modules.governance.models import SystemSetting
from app.modules.identity.access import assign_role, ensure_identity_seed
from app.modules.identity.models import User

SAMPLE_PASSWORD = "SeedSample#2026"
SEED_KEY = "seed.sample"
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

CATEGORIES = [
    ("Namkeen", None),
    ("Sev", "Namkeen"),
    ("Bhujia", "Namkeen"),
    ("Gathiya", "Namkeen"),
    ("Sweets", None),
    ("Dry sweets", "Sweets"),
    ("Milk sweets", "Sweets"),
    ("Faral", None),
    ("Festival boxes", "Faral"),
    ("Farsan mixes", None),
    ("Chutneys", None),
    ("Papad", None),
]

BRANDS = [
    "Mahavir",
    "Rajwadi",
    "Utsav",
    "Surati",
    "Anand",
    "Kesar",
    "Laxmi",
    "Shreeji",
    "Dwarka",
    "Girnar",
    "Saathvik",
    "Faral Ghar",
]

MANUFACTURERS = [
    "Mahavir Kitchen",
    "Ring Road Sweets",
    "Varachha Namkeen",
    "Katargam Faral",
    "Adajan Farsan",
    "Piplod Snacks",
    "Athwa Dry Fruit",
    "Vesu Mithai",
    "Rander Papad",
    "Udhna Sev",
    "Nanpura Jalebi",
    "Dumas Gathiya",
]

PRODUCTS = [
    ("Nylon Sev", "Sev", "SEED-001", "200g", "mild", "180.00", "160.00", "published", True),
    ("Aloo Bhujia", "Bhujia", "SEED-002", "400g", "medium", "220.00", "195.00", "published", True),
    ("Sing Bhujia", "Bhujia", "SEED-003", "250g", "hot", "240.00", "210.00", "published", True),
    ("Chakli", "Namkeen", "SEED-004", "300g", "mild", "260.00", "230.00", "published", True),
    ("Gathiya", "Gathiya", "SEED-005", "500g", "medium", "190.00", "165.00", "published", False),
    ("Fafda", "Namkeen", "SEED-006", "250g", "mild", "150.00", "135.00", "published", False),
    ("Jalebi", "Sweets", "SEED-007", "500g", "none", "320.00", "280.00", "published", True),
    ("Mohanthal", "Dry sweets", "SEED-008", "500g", "none", "480.00", "440.00", "published", True),
    ("Kaju Katli", "Dry sweets", "SEED-009", "250g", "none", "620.00", "560.00", "published", False),
    ("Diwali Faral Box", "Festival boxes", "SEED-010", "1kg", "mild", "899.00", "799.00", "draft", False),
    ("Methi Muthia Mix", "Farsan mixes", "SEED-011", "300g", "medium", "210.00", "185.00", "draft", False),
    ("Seasonal Mohanthal Tin", "Dry sweets", "SEED-012", "1kg", "none", "960.00", "880.00", "archived", False),
]

INQUIRY_STATUSES = [
    "new",
    "reviewing",
    "accepted",
    "declined",
    "converted",
    "new",
    "reviewing",
    "accepted",
    "declined",
    "converted",
    "new",
    "converted",
]

PARTNERS = [
    ("Seed Grain House", "vendor"),
    ("Seed Besan Mill", "raw_material_supplier"),
    ("Seed Oil Traders", "vendor"),
    ("Seed Sugar Depot", "raw_material_supplier"),
    ("Seed Dry Fruit Co", "vendor"),
    ("Seed Spice Yard", "raw_material_supplier"),
    ("Seed Packaging Works", "manufacturer"),
    ("Seed Tin Press", "manufacturer"),
    ("Seed Ghee Supply", "vendor"),
    ("Seed Flour Mill", "raw_material_supplier"),
    ("Seed Label Studio", "manufacturer"),
    ("Seed Carton House", "manufacturer"),
]


def main() -> None:
    settings = get_settings()
    if settings.app_env.strip().lower() == "production":
        print("Refusing to seed while APP_ENV is production.")
        raise SystemExit(2)
    email = settings.bootstrap_admin_email.strip().lower()
    password = settings.bootstrap_admin_password
    if not email or not password:
        print("Set BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD in .env before seeding.")
        raise SystemExit(2)

    with Session(get_engine()) as session:
        ensure_identity_seed(session)
        session.commit()
        actor = ensure_super_admin(session, email, password)
        if session.get(SystemSetting, SEED_KEY) is not None:
            print(f"Sample data is already present. Super Admin {email} is ready.")
            return
        try:
            sample_hash = hash_password(SAMPLE_PASSWORD)
            _staff, customers = seed_users(session, sample_hash)
            categories = seed_catalog_categories(session, actor)
            products = seed_products(session, actor, categories)
            seed_cms(session, actor, categories, products)
            seed_commerce(session, actor, customers, products)
            documents = seed_documents(session, actor)
            invoices = seed_procurement(session, actor)
            seed_notifications(session, actor, invoices, documents)
            session.add(SystemSetting(key=SEED_KEY, value_json={"version": 1}))
            record_audit(session, actor.id, "seed.sample", "system_setting", None, None, {"key": SEED_KEY})
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            print(f"This section was rolled back because a unique value already exists: {exc.orig}")
            print("Earlier sections that already saved stay in place. Fix the conflict and run the command again.")
            raise SystemExit(1) from exc

    print(f"Super Admin is ready: {email}")
    print(f"Sample password for staff and customers: {SAMPLE_PASSWORD}")
    print("Staff: staff.seed@mahavir.local")
    print("Customers: customer01@mahavir.local through customer12@mahavir.local")


def ensure_super_admin(session: Session, email: str, password: str) -> User:
    user = session.scalar(select(User).where(User.email == email))
    if user is not None:
        print(f"Super Admin {email} already exists. Password and role were left unchanged.")
        return user
    user = User(email=email, password_hash=hash_password(password), is_active=True)
    session.add(user)
    session.flush()
    assign_role(session, user.id, "super_admin")
    session.add(CustomerProfile(user_id=user.id, full_name="Super Admin", phone="9800000000"))
    record_audit(session, user.id, "user.bootstrap", "user", user.id, None, {"email": email, "source": "seed"})
    session.commit()
    print(f"Created Super Admin {email}.")
    return user


def seed_users(session: Session, sample_hash: str) -> tuple[User, list[User]]:
    staff = user_with_role(session, "staff.seed@mahavir.local", "Seed Staff", "9800000100", sample_hash, "admin")
    customers = [
        user_with_role(
            session,
            f"customer{index:02d}@mahavir.local",
            f"Seed Customer {index:02d}",
            f"9800000{index:03d}",
            sample_hash,
            "customer",
        )
        for index in range(1, 13)
    ]
    session.commit()
    return staff, customers


def user_with_role(session: Session, email: str, full_name: str, phone: str, password_hash: str, role: str) -> User:
    user = session.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, password_hash=password_hash, is_active=True)
        session.add(user)
        session.flush()
    assign_role(session, user.id, role)
    if session.scalar(select(CustomerProfile).where(CustomerProfile.user_id == user.id)) is None:
        session.add(CustomerProfile(user_id=user.id, full_name=full_name, phone=phone))
        session.flush()
    return user


def seed_catalog_categories(session: Session, actor: User) -> dict[str, Category]:
    found = {row.name: row for row in session.scalars(select(Category).where(Category.archived_at.is_(None)))}
    created = False
    for name, parent_name in CATEGORIES:
        if name in found:
            continue
        parent = found.get(parent_name) if parent_name else None
        row = Category(name=name, slug=unique_slug(session, Category, name), parent_id=parent.id if parent else None)
        session.add(row)
        session.flush()
        found[name] = row
        created = True
    if created:
        record_audit(session, actor.id, "category.create", "category", None, None, {"count": len(CATEGORIES), "source": "seed"})
    session.commit()
    return found


def seed_products(session: Session, actor: User, categories: dict[str, Category]) -> list[Product]:
    existing = session.scalar(select(Product).where(Product.sku == "SEED-001"))
    if existing is not None:
        return list(session.scalars(select(Product).where(Product.sku.like("SEED-%")).order_by(Product.sku)))
    brands = named_rows(session, Brand, BRANDS)
    makers = named_rows(session, Manufacturer, MANUFACTURERS)
    now = utc_now()
    products: list[Product] = []
    for index, (name, category_name, sku, weight, spice, mrp, price, status, featured) in enumerate(PRODUCTS):
        product = Product(
            name=name,
            slug=unique_slug(session, Product, name),
            sku=sku,
            description=f"{name} from the Mahavir sample counter.",
            manufacturer_id=makers[index % len(makers)].id,
            brand_id=brands[index % len(brands)].id,
            status=status,
            is_featured=featured,
            is_searchable=status != "archived",
            price=money(Decimal(price)),
            mrp=money(Decimal(mrp)),
            archived_at=now if status == "archived" else None,
        )
        session.add(product)
        session.flush()
        session.add(ProductCategory(product_id=product.id, category_id=categories[category_name].id))
        session.add(ProductAttribute(product_id=product.id, name="weight", value=weight))
        session.add(ProductAttribute(product_id=product.id, name="spice", value=spice))
        if index < 6 and status == "published":
            key = f"seed/products/{product.id}.png"
            get_storage().put(key, TINY_PNG, "image/png")
            session.add(ProductMedia(product_id=product.id, storage_key=key, content_type="image/png", sort_order=0, created_at=now))
        products.append(product)
    record_audit(session, actor.id, "product.create", "product", products[0].id, None, {"sku": products[0].sku, "source": "seed"})
    session.commit()
    return products


def named_rows(session: Session, model: type, names: list[str]) -> list:
    rows = []
    for name in names:
        row = session.scalar(select(model).where(model.name == name, model.archived_at.is_(None)))
        if row is None:
            row = model(name=name, slug=unique_slug(session, model, name))
            session.add(row)
            session.flush()
        rows.append(row)
    return rows


def seed_cms(session: Session, actor: User, categories: dict[str, Category], products: list[Product]) -> None:
    page = session.scalar(select(Page).where(Page.slug == "home"))
    if page is None:
        page = Page(title="Mahavir Farsan Mart", slug="home", status="published")
        session.add(page)
        session.flush()
    published_ids = [str(row.id) for row in products if row.status == "published"]
    parent_names = [name for name, parent_name in CATEGORIES if parent_name is None]
    category_ids = [str(categories[name].id) for name in parent_names if name in categories]
    existing_types = set(session.scalars(select(PageSection.type).where(PageSection.page_id == page.id)))
    sections = [
        ("hero", "Fresh farsan, every morning", "Sev, bhujia, chakli, and festival faral from the Mahavir counter.", {}),
        ("product_grid", "From the counter", "Published sample products from the shop shelves.", {"product_ids": published_ids[:8]}),
        ("category_grid", "Shop by shelf", "Namkeen, sweets, faral, and the rest of the counter.", {"category_ids": category_ids}),
        ("contact_cta", "Ask for a faral box", "Send an enquiry and the shop will confirm price and packing.", {}),
    ]
    sort_order = session.scalar(select(PageSection.sort_order).where(PageSection.page_id == page.id).order_by(PageSection.sort_order.desc()))
    next_order = 0 if sort_order is None else sort_order + 1
    added_section = False
    for kind, title, subtitle, config in sections:
        if kind in existing_types:
            continue
        session.add(
            PageSection(
                page_id=page.id,
                type=kind,
                title=title,
                subtitle=subtitle,
                sort_order=next_order,
                enabled=True,
                config_json=config,
            )
        )
        next_order += 1
        added_section = True
    if added_section and page.status != "published":
        page.status = "published"
    if session.scalar(select(Campaign).where(Campaign.slug == "seed-diwali")) is None:
        now = utc_now()
        windows = [
            ("Diwali faral", "seed-diwali", now - timedelta(days=2), now + timedelta(days=20)),
            ("Holi sweets", "seed-holi", now + timedelta(days=40), now + timedelta(days=55)),
            ("Rakhi tins", "seed-rakhi", now - timedelta(days=50), now - timedelta(days=10)),
        ]
        for name, slug, start_at, end_at in windows:
            campaign = Campaign(name=name, slug=slug, status="published", start_at=start_at, end_at=end_at, theme_json={"accent": "saffron"})
            session.add(campaign)
            session.flush()
            for sort_order, product in enumerate(row for row in products if row.status == "published"):
                if sort_order == 3:
                    break
                session.add(CampaignProduct(campaign_id=campaign.id, product_id=product.id, sort_order=sort_order))
    record_audit(session, actor.id, "page.publish", "page", page.id, None, {"slug": page.slug, "source": "seed"})
    session.commit()


def seed_commerce(session: Session, actor: User, customers: list[User], products: list[Product]) -> None:
    if session.scalar(select(Inquiry).where(Inquiry.email == "customer01@mahavir.local", Inquiry.message.like("Seed enquiry%"))) is not None:
        return
    published = [row for row in products if row.status == "published"]
    now = utc_now()
    for index, customer in enumerate(customers[:3]):
        if session.scalar(select(Cart).where(Cart.user_id == customer.id, Cart.status == "active")) is None:
            cart = Cart(user_id=customer.id, status="active")
            session.add(cart)
            session.flush()
            session.add(CartItem(cart_id=cart.id, product_id=published[index].id, quantity=index + 1))
        if session.scalar(select(Wishlist).where(Wishlist.user_id == customer.id)) is None:
            wishlist = Wishlist(user_id=customer.id)
            session.add(wishlist)
            session.flush()
            session.add(WishlistItem(wishlist_id=wishlist.id, product_id=published[index + 3].id, created_at=now))
    for index, status in enumerate(INQUIRY_STATUSES):
        customer = customers[index]
        inquiry = Inquiry(
            user_id=customer.id,
            name=f"Seed Customer {index + 1:02d}",
            phone=f"9800000{index + 1:03d}",
            email=customer.email,
            message=f"Seed enquiry {index + 1:02d} for a shop counter order.",
            status=status,
        )
        session.add(inquiry)
        session.flush()
        line_product = published[index % len(published)]
        session.add(InquiryItem(inquiry_id=inquiry.id, product_id=line_product.id, quantity=(index % 3) + 1))
        if status == "converted":
            order = Order(user_id=customer.id, inquiry_id=inquiry.id, status="requested")
            session.add(order)
            session.flush()
            session.add(
                OrderItem(
                    order_id=order.id,
                    product_id=line_product.id,
                    quantity=(index % 3) + 1,
                    unit_price=line_product.price,
                )
            )
            record_audit(session, actor.id, "inquiry.convert", "order", order.id, None, {"inquiry_id": str(inquiry.id), "source": "seed"})
    session.commit()


def seed_documents(session: Session, actor: User) -> list[Document]:
    existing = session.scalar(select(Document).where(Document.title == "Seed FSSAI license 01"))
    if existing is not None:
        return list(session.scalars(select(Document).where(Document.title.like("Seed %")).order_by(Document.title)))
    today = shop_today()
    titles = [
        "FSSAI license",
        "GST registration",
        "Shop act",
        "Legal metrology",
        "Fire NOC",
        "Trade license",
        "Udyam certificate",
        "Insurance policy",
        "Rent agreement",
        "FSSAI renewal",
        "GST return acknowledgement",
        "Weights certificate",
    ]
    documents: list[Document] = []
    now = utc_now()
    for index, title in enumerate(titles):
        if index == 0:
            expiry = today - timedelta(days=1)
        elif index < 4:
            expiry = today + timedelta(days=5 + index)
        else:
            expiry = today + timedelta(days=120 + index)
        document = Document(
            category=["fssai", "gst", "shop_act", "legal_metrology", "other"][index % 5],
            title=f"Seed {title} {index + 1:02d}",
            visibility="public" if index % 2 == 0 else "admin",
            issue_date=today - timedelta(days=200),
            expiry_date=expiry,
        )
        session.add(document)
        session.flush()
        key = f"seed/documents/{document.id}.png"
        get_storage().put(key, TINY_PNG, "image/png")
        session.add(
            DocumentVersion(
                document_id=document.id,
                storage_key=key,
                content_type="image/png",
                filename=f"seed-{index + 1:02d}.png",
                version_number=1,
                created_at=now,
            )
        )
        documents.append(document)
    record_audit(session, actor.id, "document.create", "document", documents[0].id, None, {"title": documents[0].title, "source": "seed"})
    session.commit()
    return documents


def seed_procurement(session: Session, actor: User) -> list[Invoice]:
    existing = session.scalar(select(Invoice).where(Invoice.invoice_number == "SEED-INV-01"))
    if existing is not None:
        return list(session.scalars(select(Invoice).where(Invoice.invoice_number.like("SEED-INV-%")).order_by(Invoice.invoice_number)))
    today = shop_today()
    invoices: list[Invoice] = []
    for index, (name, role) in enumerate(PARTNERS):
        partner = BusinessPartner(name=name)
        session.add(partner)
        session.flush()
        session.add(PartnerRole(partner_id=partner.id, role=role))
        session.add(Contact(partner_id=partner.id, name=f"{name} desk", phone=f"2610000{index:03d}", email=f"desk{index + 1:02d}@seed.local"))
        session.add(Address(partner_id=partner.id, line1=f"{index + 1} Ring Road", city="Surat", state="Gujarat", postal_code="395002"))
        purchase = Purchase(partner_id=partner.id, purchased_on=today - timedelta(days=index + 1))
        session.add(purchase)
        session.flush()
        amount = money(Decimal("1500.00") + Decimal(index) * Decimal("125.50"))
        session.add(PurchaseItem(purchase_id=purchase.id, description=f"Sample lot {index + 1}", amount=amount))
        status = ("open", "partial", "paid")[index % 3]
        if status == "open" and index == 0:
            due = today + timedelta(days=2)
        elif status == "open" and index == 6:
            due = today - timedelta(days=2)
        elif status == "open":
            due = today + timedelta(days=20)
        elif status == "partial":
            due = today - timedelta(days=5)
        else:
            due = today + timedelta(days=12)
        invoice = Invoice(
            purchase_id=purchase.id,
            invoice_number=f"SEED-INV-{index + 1:02d}",
            amount=amount,
            due_date=due,
            status=status,
        )
        session.add(invoice)
        session.flush()
        if status == "partial":
            session.add(Payment(invoice_id=invoice.id, amount=money(amount / Decimal(2)), paid_on=today - timedelta(days=1), method="upi", reference=f"SEED-PAY-{index + 1:02d}"))
        elif status == "paid":
            session.add(Payment(invoice_id=invoice.id, amount=amount, paid_on=today - timedelta(days=1), method="bank", reference=f"SEED-PAY-{index + 1:02d}"))
            record_audit(session, actor.id, "payment.record", "payment", invoice.id, None, {"invoice_number": invoice.invoice_number, "source": "seed"})
        invoices.append(invoice)
    session.commit()
    return invoices


def seed_notifications(session: Session, actor: User, invoices: list[Invoice], documents: list[Document]) -> None:
    ensure_default_rules(session)
    due_rule = session.scalar(select(ReminderRule).where(ReminderRule.condition_type == "payment_due"))
    overdue_rule = session.scalar(select(ReminderRule).where(ReminderRule.condition_type == "payment_overdue"))
    expiry_rule = session.scalar(select(ReminderRule).where(ReminderRule.condition_type == "document_expiry"))
    now = utc_now()
    targets = [
        (due_rule, "invoice", invoices[0].id),
        (overdue_rule, "invoice", invoices[1].id),
        (expiry_rule, "document", documents[0].id),
        (expiry_rule, "document", documents[1].id),
    ]
    for rule, entity_type, entity_id in targets:
        if rule is None:
            continue
        already = session.scalar(
            select(Reminder).where(Reminder.rule_id == rule.id, Reminder.entity_type == entity_type, Reminder.entity_id == entity_id)
        )
        if already is None:
            session.add(Reminder(rule_id=rule.id, entity_type=entity_type, entity_id=entity_id, status="open", generated_at=now))
    record_audit(session, actor.id, "reminder.rule", "reminder_rule", None, None, {"source": "seed"})


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        print(f"Seed failed: {exc}")
        sys.exit(1)
