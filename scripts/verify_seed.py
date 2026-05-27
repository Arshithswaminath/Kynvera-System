import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from Injaaz import create_app
from app.models import TicketProject, TicketProperty, TicketZone, TicketSubZone, TicketBaseUnit, TicketTitleTemplate
app = create_app()
with app.app_context():
    print('Projects:       ', TicketProject.query.count())
    print('Properties:     ', TicketProperty.query.count())
    print('Zones:          ', TicketZone.query.count())
    print('Sub-zones:      ', TicketSubZone.query.count())
    print('Base units:     ', TicketBaseUnit.query.count())
    print('Title templates:', TicketTitleTemplate.query.count())
    print('')
    print('-- Projects --')
    for p in TicketProject.query.all():
        print(f'  [{p.id}] {p.name}')
    print('')
    print('-- Title Templates (first 5) --')
    for t in TicketTitleTemplate.query.limit(5).all():
        print(f'  [{t.id}] {t.title}')
