"""Dedicated procurement / store-keeping tables.

Imported from app.models so db.create_all() picks them up.
Inventory no longer lives in Submission.form_data.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import UniqueConstraint

from app.models import db


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


TRADE_DEPARTMENTS = ('HVAC', 'Cleaning', 'Electrical', 'Plumbing')
GM_APPROVAL_AED = 1000.0
PR_STATUSES = (
    'draft', 'submitted', 'procurement_review', 'awaiting_quotation',
    'gm_review', 'approved', 'rejected', 'ordered', 'received', 'closed', 'cancelled',
)
QUOTATION_KINDS = ('quotation', 'quotation_2', 'quotation_3')
MAX_QUOTATIONS = 3
DOC_KINDS = ('pr_pdf', 'quotation', 'quotation_2', 'quotation_3', 'invoice')
DOC_STATUSES = ('missing', 'uploaded', 'pending_approval', 'approved')
EMAIL_EVENT_KEYS = (
    'quotation_for_approval',
    'quotation_approved',
    'invoice_for_approval',
    'invoice_approved',
)
MOVEMENT_TYPES = ('receipt', 'issue', 'return', 'adjust', 'transfer')


class ProcSupplier(db.Model):
    __tablename__ = 'proc_suppliers'

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(40), unique=True, nullable=False, index=True)
    name = db.Column(db.String(160), nullable=False)
    contact_name = db.Column(db.String(160), nullable=True)
    contact_email = db.Column(db.String(255), nullable=True)
    contact_phone = db.Column(db.String(80), nullable=True)
    trades = db.Column(db.String(255), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=_utcnow)

    def to_dict(self):
        return {
            'id': self.public_id,
            'db_id': self.id,
            'name': self.name,
            'contact_name': self.contact_name or '',
            'contact_email': self.contact_email or '',
            'contact_phone': self.contact_phone or '',
            'trades': self.trades or '',
            'notes': self.notes or '',
            'is_active': bool(self.is_active),
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class ProcCatalogItem(db.Model):
    __tablename__ = 'proc_catalog_items'

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(40), unique=True, nullable=False, index=True)
    department = db.Column(db.String(80), nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    brand = db.Column(db.String(160), nullable=True)
    uom = db.Column(db.String(40), default='PCS')
    unit_price = db.Column(db.Float, default=0.0)
    min_qty = db.Column(db.Float, default=0.0)
    preferred_supplier_id = db.Column(db.Integer, db.ForeignKey('proc_suppliers.id'), nullable=True)
    is_rate_card = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    preferred_supplier = db.relationship('ProcSupplier', backref=db.backref('catalog_items', lazy='dynamic'))

    def to_catalog_dict(self):
        return {
            'id': self.public_id,
            'db_id': self.id,
            'name': self.name,
            'brand': self.brand or '',
            'uom': self.uom or 'PCS',
            'unit_price': float(self.unit_price or 0),
            'department': self.department,
            'min_qty': float(self.min_qty or 0),
            'preferred_supplier_id': self.preferred_supplier.public_id if self.preferred_supplier else None,
        }


class ProcProperty(db.Model):
    __tablename__ = 'proc_properties'

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(40), unique=True, nullable=False, index=True)
    name = db.Column(db.String(160), nullable=False, index=True)
    address = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=True)
    ticket_property_id = db.Column(db.Integer, nullable=True)
    is_shared = db.Column(db.Boolean, default=False, index=True)
    icon = db.Column(db.String(32), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)

    def to_dict(self):
        return {
            'id': self.public_id,
            'db_id': self.id,
            'name': self.name,
            'address': self.address or '',
            'description': self.description or '',
            'ticket_property_id': self.ticket_property_id,
            'is_shared': bool(self.is_shared),
            'icon': self.icon or '',
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class ProcStock(db.Model):
    __tablename__ = 'proc_stock'
    __table_args__ = (
        UniqueConstraint('property_id', 'catalog_item_id', name='uq_proc_stock_property_item'),
    )

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(40), unique=True, nullable=False, index=True)
    property_id = db.Column(db.Integer, db.ForeignKey('proc_properties.id'), nullable=False, index=True)
    catalog_item_id = db.Column(db.Integer, db.ForeignKey('proc_catalog_items.id'), nullable=False, index=True)
    qty_on_hand = db.Column(db.Float, default=0.0)
    notes = db.Column(db.Text, nullable=True)
    added_by = db.Column(db.String(160), nullable=True)
    imported_from_excel = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    property = db.relationship('ProcProperty', backref=db.backref('stock_rows', lazy='dynamic'))
    catalog_item = db.relationship('ProcCatalogItem', backref=db.backref('stock_rows', lazy='dynamic'))

    def to_material_dict(self):
        item = self.catalog_item
        prop = self.property
        qty = float(self.qty_on_hand or 0)
        price = float(item.unit_price or 0) if item else 0.0
        return {
            'id': self.public_id,
            'material_name': item.name if item else '',
            'property': prop.name if prop else 'Unassigned',
            'category': item.department if item else 'General',
            'description': self.notes or '',
            'unit': (item.uom if item else 'PCS') or 'PCS',
            'quantity': qty,
            'unit_price': price,
            'total_price': qty * price,
            'supplier': (item.preferred_supplier.name if item and item.preferred_supplier else ''),
            'notes': self.notes or '',
            'added_by': self.added_by or '',
            'imported_from_excel': bool(self.imported_from_excel),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'catalog_id': item.public_id if item else None,
            'brand': (item.brand if item else '') or '',
        }


class ProcPurchaseRequest(db.Model):
    __tablename__ = 'proc_purchase_requests'

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(40), unique=True, nullable=False, index=True)
    status = db.Column(db.String(40), default='submitted', index=True)
    property_id = db.Column(db.Integer, db.ForeignKey('proc_properties.id'), nullable=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('proc_suppliers.id'), nullable=True)
    requested_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    reject_reason = db.Column(db.Text, nullable=True)
    total_aed = db.Column(db.Float, default=0.0)
    needs_gm = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)
    approved_at = db.Column(db.DateTime, nullable=True)
    ordered_at = db.Column(db.DateTime, nullable=True)
    received_at = db.Column(db.DateTime, nullable=True)

    property = db.relationship('ProcProperty')
    supplier = db.relationship('ProcSupplier')
    requested_by = db.relationship('User', foreign_keys=[requested_by_id])
    lines = db.relationship(
        'ProcPurchaseLine', backref='request', lazy='joined',
        cascade='all, delete-orphan', order_by='ProcPurchaseLine.id',
    )
    documents = db.relationship(
        'ProcPurchaseDocument', backref='request', lazy='dynamic',
        cascade='all, delete-orphan',
    )

    def to_dict(self, with_lines=True):
        d = {
            'id': self.public_id,
            'db_id': self.id,
            'status': self.status,
            'property': self.property.name if self.property else '',
            'property_id': self.property.public_id if self.property else None,
            'supplier': self.supplier.name if self.supplier else '',
            'supplier_id': self.supplier.public_id if self.supplier else None,
            'requested_by': (self.requested_by.full_name or self.requested_by.username) if self.requested_by else '',
            'notes': self.notes or '',
            'reject_reason': self.reject_reason or '',
            'total_aed': float(self.total_aed or 0),
            'needs_gm': bool(self.needs_gm),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'approved_at': self.approved_at.isoformat() if self.approved_at else None,
            'ordered_at': self.ordered_at.isoformat() if self.ordered_at else None,
            'received_at': self.received_at.isoformat() if self.received_at else None,
        }
        if with_lines:
            d['lines'] = [ln.to_dict() for ln in self.lines]
        return d


class ProcPurchaseLine(db.Model):
    __tablename__ = 'proc_purchase_lines'

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey('proc_purchase_requests.id', ondelete='CASCADE'), nullable=False, index=True)
    catalog_item_id = db.Column(db.Integer, db.ForeignKey('proc_catalog_items.id'), nullable=False)
    qty = db.Column(db.Float, default=1.0)
    unit_price = db.Column(db.Float, default=0.0)

    catalog_item = db.relationship('ProcCatalogItem')

    def to_dict(self):
        item = self.catalog_item
        qty = float(self.qty or 0)
        price = float(self.unit_price or 0)
        return {
            'id': self.id,
            'catalog_id': item.public_id if item else None,
            'name': item.name if item else '',
            'brand': (item.brand if item else '') or '',
            'uom': (item.uom if item else 'PCS') or 'PCS',
            'department': item.department if item else '',
            'qty': qty,
            'unit_price': price,
            'line_total': qty * price,
        }


class ProcGoodsReceipt(db.Model):
    __tablename__ = 'proc_goods_receipts'

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(40), unique=True, nullable=False, index=True)
    request_id = db.Column(db.Integer, db.ForeignKey('proc_purchase_requests.id'), nullable=False, index=True)
    received_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)

    request = db.relationship('ProcPurchaseRequest', backref=db.backref('receipts', lazy='dynamic'))
    received_by = db.relationship('User', foreign_keys=[received_by_id])
    lines = db.relationship(
        'ProcGoodsReceiptLine', backref='receipt', lazy='joined',
        cascade='all, delete-orphan',
    )

    def to_dict(self):
        return {
            'id': self.public_id,
            'request_id': self.request.public_id if self.request else None,
            'notes': self.notes or '',
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'lines': [ln.to_dict() for ln in self.lines],
        }


class ProcGoodsReceiptLine(db.Model):
    __tablename__ = 'proc_goods_receipt_lines'

    id = db.Column(db.Integer, primary_key=True)
    receipt_id = db.Column(db.Integer, db.ForeignKey('proc_goods_receipts.id', ondelete='CASCADE'), nullable=False, index=True)
    catalog_item_id = db.Column(db.Integer, db.ForeignKey('proc_catalog_items.id'), nullable=False)
    qty = db.Column(db.Float, default=0.0)

    catalog_item = db.relationship('ProcCatalogItem')

    def to_dict(self):
        item = self.catalog_item
        return {
            'catalog_id': item.public_id if item else None,
            'name': item.name if item else '',
            'qty': float(self.qty or 0),
        }


class ProcMovement(db.Model):
    __tablename__ = 'proc_movements'

    id = db.Column(db.Integer, primary_key=True)
    movement_type = db.Column(db.String(20), nullable=False, index=True)
    property_id = db.Column(db.Integer, db.ForeignKey('proc_properties.id'), nullable=True)
    catalog_item_id = db.Column(db.Integer, db.ForeignKey('proc_catalog_items.id'), nullable=True)
    qty = db.Column(db.Float, default=0.0)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    ticket_id = db.Column(db.Integer, nullable=True)
    request_id = db.Column(db.Integer, db.ForeignKey('proc_purchase_requests.id'), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)

    property = db.relationship('ProcProperty')
    catalog_item = db.relationship('ProcCatalogItem')
    user = db.relationship('User', foreign_keys=[user_id])

    def to_activity_dict(self):
        item = self.catalog_item
        who = ''
        if self.user:
            who = self.user.full_name or self.user.username
        return {
            'material_name': item.name if item else (self.notes or 'Stock movement'),
            'submitted_by': who or 'System',
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'movement_type': self.movement_type,
            'qty': float(self.qty or 0),
            'property': self.property.name if self.property else '',
        }


class ProcPurchaseDocument(db.Model):
    __tablename__ = 'proc_purchase_documents'
    __table_args__ = (
        UniqueConstraint('request_id', 'kind', name='uq_proc_purchase_doc_kind'),
    )

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(
        db.Integer,
        db.ForeignKey('proc_purchase_requests.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    kind = db.Column(db.String(40), nullable=False, index=True)
    original_path = db.Column(db.String(500), nullable=True)
    original_name = db.Column(db.String(255), nullable=True)
    stamped_path = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(40), default='missing', index=True)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    approved_by = db.Column(db.String(160), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    approval_token = db.Column(db.String(64), nullable=True, unique=True, index=True)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    uploaded_by = db.relationship('User', foreign_keys=[uploaded_by_id])

    def to_dict(self):
        slot = QUOTATION_KINDS.index(self.kind) + 1 if self.kind in QUOTATION_KINDS else 1
        return {
            'kind': self.kind,
            'slot': slot,
            'status': self.status or 'missing',
            'original_name': self.original_name or '',
            'has_original': bool(self.original_path),
            'has_stamped': bool(self.stamped_path) and self.status == 'approved',
            'approved_by': self.approved_by or '',
            'approved_at': self.approved_at.isoformat() if self.approved_at else None,
        }


class ProcEmailTemplate(db.Model):
    __tablename__ = 'proc_email_templates'

    id = db.Column(db.Integer, primary_key=True)
    event_key = db.Column(db.String(80), unique=True, nullable=False, index=True)
    to_emails = db.Column(db.Text, nullable=True)
    cc_emails = db.Column(db.Text, nullable=True)
    subject = db.Column(db.String(255), nullable=True)
    body = db.Column(db.Text, nullable=True)
    attach_pdf = db.Column(db.Boolean, default=True)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    def to_dict(self):
        return {
            'event_key': self.event_key,
            'to_emails': self.to_emails or '',
            'cc_emails': self.cc_emails or '',
            'subject': self.subject or '',
            'body': self.body or '',
            'attach_pdf': self.attach_pdf is not False,
        }
