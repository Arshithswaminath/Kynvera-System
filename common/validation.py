"""
Request validation schemas for all modules
"""
from marshmallow import Schema, fields, validates, ValidationError, validate
from datetime import date

class HVACItemSchema(Schema):
    """Schema for HVAC/MEP inspection items"""
    asset = fields.Str(required=True, validate=validate.Length(min=1, max=200))
    system = fields.Str(required=True, validate=validate.Length(min=1, max=200))
    description = fields.Str(required=True, validate=validate.Length(min=1, max=1000))
    quantity = fields.Str(required=False, allow_none=True, validate=validate.Length(max=50))
    brand = fields.Str(required=False, allow_none=True, validate=validate.Length(max=200))
    specification = fields.Str(required=False, allow_none=True, validate=validate.Length(max=500))
    comments = fields.Str(required=False, allow_none=True, validate=validate.Length(max=1000))
    photo_urls = fields.List(fields.URL(), required=False)

class HVACSubmissionSchema(Schema):
    """Schema for HVAC/MEP form submission"""
    site_name = fields.Str(required=True, validate=validate.Length(min=1, max=200))
    visit_date = fields.Date(required=True)
    tech_signature = fields.Str(required=False, allow_none=True)
    opMan_signature = fields.Str(required=False, allow_none=True)
    supervisor_signature = fields.Str(required=False, allow_none=True)
    supervisor_comments = fields.Str(required=False, allow_none=True, validate=validate.Length(max=2000))
    items = fields.List(fields.Nested(HVACItemSchema), required=True, validate=validate.Length(min=1))
    
    @validates('visit_date')
    def validate_visit_date(self, value):
        """Ensure visit date is not in the future"""
        if value > date.today():
            raise ValidationError("Visit date cannot be in the future")

class PhotoUploadSchema(Schema):
    """Schema for individual photo upload"""
    photo = fields.Raw(required=True)  # File upload

def validate_request(schema_class, data):
    """
    Validate request data against a schema
    
    Args:
        schema_class: Marshmallow schema class
        data: Dictionary to validate
        
    Returns:
        (is_valid, validated_data_or_errors)
    """
    schema = schema_class()
    try:
        validated = schema.load(data)
        return True, validated
    except ValidationError as err:
        return False, err.messages
