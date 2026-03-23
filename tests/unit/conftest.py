"""
Unit test configuration.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from finbot.main import app
from finbot.core.auth.session import session_manager
from finbot.core.data.database import Base
from finbot.core.data.repositories import VendorRepository, InvoiceRepository
from finbot.core.data.models import UserSession
from sqlalchemy.pool import StaticPool

# Use in-memory SQLite for tests
TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def engine():
    """Create test database engine with fresh tables each time"""
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # Ensures the same connection is used

    )
    return engine


@pytest.fixture
def client():
    """Test client for unit tests.

    Overrides the global client fixture. Mocks the CTF event processor
    and definition loader to prevent CancelledError from async background
    tasks during test teardown.
    """
    with patch("finbot.main.start_processor_task", return_value=None):
        with TestClient(app) as test_client:
            yield test_client


@pytest.fixture
def fast_client(client):
    """Alias for client fixture for unit tests."""
    return client


@pytest.fixture(scope="function")
def db(engine, monkeypatch):
    """Database session with automatic cleanup between tests
    
    This fixture:
    1. Creates fresh in-memory database for each test
    2. Creates all tables before test
    3. Patches SessionLocal to use test database (critical for session_manager)
    4. Yields clean session for test
    5. Drops all tables after test completes
    """
    # Create all tables before test
    Base.metadata.create_all(bind=engine)
    
    # Create test session factory
    TestSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine
    )
    
    # Patch the global SessionLocal used by session_manager and repositories
    monkeypatch.setattr(
        "finbot.core.data.database.SessionLocal",
        TestSessionLocal,
    )
    monkeypatch.setattr(
        "finbot.core.auth.session.SessionLocal",
        TestSessionLocal,
    )
    
    session = TestSessionLocal()
    
    yield session
    
    # Cleanup after test
    session.close()
    Base.metadata.drop_all(bind=engine)


def create_vendor(vendor_repo, company_name: str, contact_name: str, email: str, tin: str):
    """Helper to create a vendor with standard test data."""
    return vendor_repo.create_vendor(
        company_name=company_name,
        vendor_category="Technology",
        industry="Software",
        services="Consulting",
        contact_name=contact_name,
        email=email,
        tin=tin,
        bank_account_number="123456789012",
        bank_name="Test Bank",
        bank_routing_number="021000021",
        bank_account_holder_name=contact_name,
    )


@pytest.fixture
def vendor_pair_setup(db):
    """Create two test vendors with sessions for isolation testing.

    Returns dict with:
        - s1, s2: Two sessions for same user email
        - v1, v2: Two vendors created in same namespace
        - db: Database session
    """
    s1 = session_manager.create_session(email="isolation_test@example.com")
    s2 = session_manager.create_session(email="isolation_test@example.com")

    vendor_repo = VendorRepository(db, s1)
    v1 = create_vendor(vendor_repo, "Vendor Alpha", "Alice Smith", "alice@vendor1.com", "11-1111111")
    v2 = create_vendor(vendor_repo, "Vendor Beta", "Bob Johnson", "bob@vendor2.com", "22-2222222")

    us1 = db.query(UserSession).filter(UserSession.session_id == s1.session_id).first()
    us2 = db.query(UserSession).filter(UserSession.session_id == s2.session_id).first()
    us1.current_vendor_id = v1.id
    us2.current_vendor_id = v2.id
    db.commit()

    return {
        's1': s1,
        's2': s2,
        'v1': v1,
        'v2': v2,
        'db': db,
    }


@pytest.fixture
def multi_vendor_setup(db):
    """Create multiple test vendors for load/concurrency testing.

    Returns dict with:
        - vendors: List of vendor dicts with session_id, vendor_id, invoice_id
        - db: Database session
    """
    vendors = []
    
    # Create 5 vendors, each with their own session and unique identity
    for i in range(5):
        # Each vendor gets a distinct session (separate user email)
        session = session_manager.create_session(email=f"vendor_{i}@example.com")
        vendor_repo = VendorRepository(db, session)

        # Create vendor with unique test data per iteration
        vendor = create_vendor(
            vendor_repo,
            f"Load Test Vendor {i}",
            f"Contact {i}",
            f"contact{i}@example.com",
            f"{i:02d}-{i:07d}"
        )
        
        # Track each vendor's context for use in tests
        vendors.append({
            'session_id': session.session_id,
            'vendor_id': vendor.id,
            'invoice_id': None,  # Placeholder for tests that need invoices
            'db': db,
        })
    
    return vendors

@pytest.fixture(autouse=True)
def clean_db(db):
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())
    db.commit()
