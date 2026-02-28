-- CGCS Event Space Automation Engine
-- Seed data: pricing tiers and room configurations

SET search_path TO cgcs, public;

-- Pricing rules
INSERT INTO cgcs.pricing_rules (tier, hourly_rate, minimum_hours, description) VALUES
    ('acc_internal', 0.00, 1, 'ACC internal departments and programs — no charge'),
    ('government_agency', 0.00, 1, 'Federal, state, and local government agencies — no charge'),
    ('nonprofit', 25.00, 2, 'Nonprofit organizations with civic/government missions'),
    ('community_partner', 50.00, 2, 'Community partners with educational missions'),
    ('external', 100.00, 3, 'External organizations — standard rate');

-- Room configurations
INSERT INTO cgcs.room_configurations (room, display_name, max_capacity, available_equipment, setup_options, google_calendar_id) VALUES
    ('large_conference', 'Large Conference Room', 60,
     '{"projector": true, "screen": true, "whiteboard": true, "microphone": true, "speakers": true, "video_conferencing": true, "wifi": true}',
     '{"theater": 60, "classroom": 30, "boardroom": 24, "u_shape": 20, "banquet": 40}',
     'REPLACE_WITH_GOOGLE_CALENDAR_ID'),
    ('small_conference', 'Small Conference Room', 15,
     '{"projector": true, "screen": true, "whiteboard": true, "video_conferencing": true, "wifi": true}',
     '{"boardroom": 15, "u_shape": 10}',
     'REPLACE_WITH_GOOGLE_CALENDAR_ID'),
    ('event_hall', 'Event Hall', 200,
     '{"projector": true, "screen": true, "microphone": true, "speakers": true, "stage": true, "wifi": true, "catering_kitchen": true}',
     '{"theater": 200, "banquet": 120, "reception": 150, "classroom": 80}',
     'REPLACE_WITH_GOOGLE_CALENDAR_ID'),
    ('classroom', 'Classroom', 40,
     '{"projector": true, "screen": true, "whiteboard": true, "wifi": true}',
     '{"classroom": 40, "theater": 40, "u_shape": 20}',
     'REPLACE_WITH_GOOGLE_CALENDAR_ID'),
    ('multipurpose', 'Multipurpose Room', 80,
     '{"projector": true, "screen": true, "whiteboard": true, "microphone": true, "speakers": true, "wifi": true}',
     '{"theater": 80, "classroom": 40, "banquet": 50, "reception": 70}',
     'REPLACE_WITH_GOOGLE_CALENDAR_ID');
