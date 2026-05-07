"""
Create ticketing module tables: tickets, ticket_notes, ticket_images,
ticket_labor, ticket_materials.

Run: python migrations/add_ticketing_tables.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Injaaz import create_app
from app.models import (
    db, Ticket, TicketNote, TicketImage, TicketLabor, TicketMaterial,
)


def migrate_up():
    app = create_app()
    with app.app_context():
        engine = db.engine
        Ticket.__table__.create(bind=engine, checkfirst=True)
        TicketNote.__table__.create(bind=engine, checkfirst=True)
        TicketImage.__table__.create(bind=engine, checkfirst=True)
        TicketLabor.__table__.create(bind=engine, checkfirst=True)
        TicketMaterial.__table__.create(bind=engine, checkfirst=True)
        print('[OK] ticketing tables ready')


if __name__ == '__main__':
    migrate_up()
