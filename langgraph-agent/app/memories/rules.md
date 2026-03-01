# CGCS Email Triage Rules

## Email Categories

### 1. event_request
- Someone requesting to reserve or book event space
- Inquiries about availability for specific dates
- Requests to modify existing reservations

### 2. intake_followup
- Follow-up to an existing intake or reservation
- References to existing request IDs or previous conversations
- "Just checking on..." or "Any update on..." emails

### 3. aais_receipt
- From Ad Astra (notifications@aais.com, noreply@aais.com)
- Auto-classify, mark read
- Only surface emails with subject containing "has been approved"
- Extract reservation # from subject (format: Event Reservation #YYYYMMDD-NNNNN)

### 4. smartsheet_notification
- Usually from Michelle Raymond (michelle.raymond@austincc.edu)
- Routes clients via Smartsheet
- Always high priority

### 5. calendar_invite
- Contains .ics attachment or calendar invite markers
- DO NOT auto-accept or decline
- Leave alone — Austin handles manually

### 6. question
- General questions about CGCS services, facilities, pricing
- Questions about facility capabilities or equipment

### 7. follow_up
- Generic follow-ups not tied to a specific intake
- Responses to previous CGCS communications

### 8. complaint
- Negative feedback about past events or experiences
- Issues with facilities or equipment during events
- Billing disputes

### 9. vendor
- Vendor inquiries, quotes, or proposals
- Service provider communications

### 10. spam
- Marketing emails
- Unsolicited vendor pitches
- Phishing attempts
- Mass mailings not relevant to CGCS

### 11. other
- Anything not fitting the above categories
- Internal ACC communications not event-related

## Priority Classification

### High Priority
- VIP sender: michelle.raymond@austincc.edu (always high priority)
- VIP keyword: "Office of the Chancellor" (always high priority)
- Events within 14 days
- Complaints

### Medium Priority
- Standard event requests
- General questions
- Follow-ups on pending requests

### Low Priority
- General/informational inquiries
- Spam
- Non-urgent vendor communications

## VIP Rules
- michelle.raymond@austincc.edu: Always high priority. ACC Strategic Planning, routes clients via Smartsheet.
- Office of the Chancellor: Always high priority (keyword match in subject/body).

## Ad Astra Rules
- Emails from notifications@aais.com or noreply@aais.com: auto-classify as aais_receipt
- Mark read automatically
- Only surface if subject contains "has been approved"
- Extract reservation # from subject line

## Calendar Invite Rules
- NEVER auto-accept or decline calendar invites
- Leave them alone for Austin to handle manually

## Reply Drafting Rules
- All outbound emails from austin.wells@austincc.edu (NOT from Zoho directly)
- Generate 3+ suggested replies per intake
- Attach both user agreement PDFs to initial responses
- Send parking map early in the process
- Never CC Bryan Port on emails
- Remove Annamelly Ortiz from all processes
- 3 business day response commitment

## Event Type Detection
- S-EVENT: Service/partner/internal (no revenue)
- C-EVENT: CGCS programs
- A-EVENT: Paid/AMI (revenue-generating)

## Auto-Send Allowlist
These addresses can receive auto-generated replies without admin approval:
- stefano.casafrancalaos@austincc.edu
- marisela.perez@austincc.edu

## Response Tone
- Professional, warm, and representative of ACC
- Sign as Austin Wells, Strategic Planner for Community Relations & Environmental Affairs
- Include contact info for further questions
- Reference CGCS website: www.cgcsacc.org
