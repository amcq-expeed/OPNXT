# Backlog for Healthcare Appointment System

## Epics
### Epic 1: Appointment Management
- **Feature 1.1:** Online Appointment Booking
  - **User Story 1.1.1:** As a patient, I want to book an appointment online so that I can schedule my visits conveniently.
    - **Acceptance Criteria:**
      - Given I am a registered patient, when I access the booking page, then I should see available time slots.
      - Given I select a time slot, when I confirm the appointment, then I should receive a confirmation message.
      - Given I book an appointment, when I check my appointment history, then I should see the newly booked appointment.
      - Given I am a patient, when I try to book an appointment outside of working hours, then I should see an error message.

- **Feature 1.2:** Appointment Reminders
  - **User Story 1.2.1:** As a patient, I want to receive appointment reminders via SMS and email so that I do not forget my appointments.
    - **Acceptance Criteria:**
      - Given I have an upcoming appointment, when the reminder is sent, then I should receive an SMS and an email notification.
      - Given I have opted out of reminders, when the reminder is sent, then I should not receive any notifications.
      - Given I have changed my contact information, when the reminder is sent, then it should be sent to the updated contact details.
      - Given I have a scheduled appointment, when I check my notifications, then I should see the reminder listed.

### Epic 2: Patient History Tracking
- **Feature 2.1:** Accessing Patient History
  - **User Story 2.1.1:** As an administrative staff member, I want to access patient history so that I can assist patients effectively.
    - **Acceptance Criteria:**
      - Given I am logged in as administrative staff, when I search for a patient, then I should see their medical records and visit summaries.
      - Given I access a patient’s history, when I view their records, then I should see the information organized by date.
      - Given I am viewing a patient’s history, when I try to access a record without proper permissions, then I should see an access denied message.
      - Given I have accessed a patient’s history, when I log out, then my session should end securely.

## Assumptions & Open Questions
- Users will have access to the necessary devices to interact with the system.
- What specific EHR systems or payment processing services will be integrated?
- What types of reports or analytics are required?