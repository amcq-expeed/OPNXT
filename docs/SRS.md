# Software Requirements Specification (SRS)

- Standard: IEEE 29148 (adapted)
- Generated: 2025-09-17T17:52:24.124728Z

## 1. Introduction
### 1.1 Purpose
Provide a detailed description of the software requirements.

### 1.2 Scope
Planning summary based on inputs:
- Goal: Business Requirements: Ohio Tech Day Event Management Platform
Project Overview
Build a simple CRUD event management application using Apptor low-code platform to support Ohio Tech Day activities, enabling administrators to gather ideas, manage execution, and inspire participation in tech education events across Ohio.
Primary Users
•	Current Phase: Administrators only
•	Future Phase: Client-facing functionality for teachers, companies, and students
Core Functionality Requirements
Event Management
Event Types to Support:
•	Class visits
•	Field trips
•	Company visits
•	Virtual events
•	Miscellaneous activities
Event Data Fields:
•	Event type classification
•	Host information
•	Date/time details
•	Location/venue
•	Description and requirements
Host Management
Host Profiles Include:
•	Organization name
•	County location
•	Website URL
•	Industry classification
•	Organization type (Company vs Non-Profit)
User Types & Roles
•	Teachers: Event participants and requesters
•	Companies: Event hosts and sponsors
•	Administrators: Platform managers
Request System
Request Types:
•	School visit requests (companies visiting schools)
•	Reverse visit requests (schools visiting companies)
•	Sponsorship requests
Conference Management
Annual Conference Data:
•	Year and title
•	Theme and description
•	Venue and dates (start/end)
•	Pre-event activities
•	During-event activities
•	Post-event activities
Search & Discovery
•	Location-based event search ("I'm in Westerville, find me something to do")
•	Member directory with contact preferences
•	Event filtering by type, location, date
Sponsorship Management
•	Sponsor profile creation
•	Sponsorship opportunity matching
•	Sponsor form completion with option selection
Automation & Communication Features
Email Templates & Notifications
•	Customizable email templates for different scenarios
•	Automated teacher notifications for sticker programs
•	Event reminder system for hosts and participants
•	Pre-event instruction emails
•	Follow-up communication templates
Dashboard & Reporting
•	Daily activity summaries powered by AI
•	Event participation tracking
•	Social media integration (hashtag aggregation)
•	Screenshot/media archiving from events
Notification System
Automated Triggers:
•	Sticker request submissions
•	Event registration confirmations
•	Pre-event reminders
•	Host introduction emails at event start
•	Post-event follow-ups
Technical Considerations
•	Built on Apptor low-code platform
•	CRUD operations for all major entities
•	Integration capabilities for social media feeds
•	Email automation functionality
•	Search and filtering capabilities
•	Media storage for event documentation
Success Metrics
•	Increased event participation across Ohio
•	Streamlined event coordination process
•	Enhanced teacher engagement with tech companies
•	Improved sponsor-event matching
•	Better tracking and reporting of tech education activities
This platform will serve as the foundation for inspiring and coordinating Ohio Tech Day activities while providing administrators with the tools needed to manage the growing network of tech education partnerships across the state.
- Stakeholder: Teachers: Event participants and requesters
- Stakeholder: Companies: Event hosts and sponsors
- Stakeholder: Administrators: Platform managers
- Primary Users: Current Phase: Administrators only
- Primary Users: Future Phase: Client-facing functionality for teachers, companies, and students

### 1.3 Definitions, Acronyms, and Abbreviations
- TBD

## 2. Overall Description
### 2.1 Product Perspective
Design summary based on inputs:
- Technical consideration: Built on Apptor low-code platform
- Technical consideration: CRUD operations for all major entities
- Technical consideration: Integration capabilities for social media feeds
- Technical consideration: Email automation functionality
- Technical consideration: Search and filtering capabilities
- Technical consideration: Media storage for event documentation
- Platform: Apptor low-code. Model-driven CRUD for entities.
- Entities: Event, Host, Request, Sponsor, Conference, User.
- Integrations: Email service, social media aggregation, storage for media artifacts.
- Search: Location + filters by type/date, directory lookup.

### 2.2 Product Functions
- The system SHALL support event type: Class visits.
- The system SHALL support event type: Field trips.
- The system SHALL support event type: Company visits.
- The system SHALL support event type: Virtual events.
- The system SHALL support event type: Miscellaneous activities.
- The system SHALL store event data field: Event type classification.
- The system SHALL store event data field: Host information.
- The system SHALL store event data field: Date/time details.
- The system SHALL store event data field: Location/venue.
- The system SHALL store event data field: Description and requirements.
- The system SHALL maintain host profile field: Organization name.
- The system SHALL maintain host profile field: County location.
- The system SHALL maintain host profile field: Website URL.
- The system SHALL maintain host profile field: Industry classification.
- The system SHALL maintain host profile field: Organization type (Company vs Non-Profit).
- The system SHALL support request type: School visit requests (companies visiting schools).
- The system SHALL support request type: Reverse visit requests (schools visiting companies).
- The system SHALL support request type: Sponsorship requests.
- The system SHALL provide discovery capability: Location-based event search ("I'm in Westerville, find me something to do").
- The system SHALL provide discovery capability: Member directory with contact preferences.
- The system SHALL provide discovery capability: Event filtering by type, location, date.
- The system SHALL support sponsorship capability: Sponsor profile creation.
- The system SHALL support sponsorship capability: Sponsorship opportunity matching.
- The system SHALL support sponsorship capability: Sponsor form completion with option selection.
- The system SHALL provide email/notification capability: Customizable email templates for different scenarios.
- The system SHALL provide email/notification capability: Automated teacher notifications for sticker programs.
- The system SHALL provide email/notification capability: Event reminder system for hosts and participants.
- The system SHALL provide email/notification capability: Pre-event instruction emails.
- The system SHALL provide email/notification capability: Follow-up communication templates.
- The system SHALL provide reporting capability: Daily activity summaries powered by AI.
- The system SHALL provide reporting capability: Event participation tracking.
- The system SHALL provide reporting capability: Social media integration (hashtag aggregation).
- The system SHALL provide reporting capability: Screenshot/media archiving from events.
- Success Metric: Increased event participation across Ohio
- Success Metric: Streamlined event coordination process
- Success Metric: Enhanced teacher engagement with tech companies
- Success Metric: Improved sponsor-event matching
- Success Metric: Better tracking and reporting of tech education activities
- Success Metric: This platform will serve as the foundation for inspiring and coordinating Ohio Tech Day activities while providing administrators with the tools needed to manage the growing network of tech education partnerships across the state.
- The system SHALL maintain conference data: Year and title.
- The system SHALL maintain conference data: Theme and description.
- The system SHALL maintain conference data: Venue and dates (start/end).
- The system SHALL maintain conference data: Pre-event activities.
- The system SHALL maintain conference data: During-event activities.
- The system SHALL maintain conference data: Post-event activities.
- NFR - Performance: First render within 2.5s on a typical broadband connection.
- NFR - Accessibility: Page meets WCAG 2.1 AA for color contrast and alt text on images.
- NFR - Privacy: Do not persist PII beyond recipient name in the client; no server storage by default.

### 2.3 User Classes and Characteristics
- Stakeholders/Users: Stakeholder: Teachers: Event participants and requesters

### 2.4 Operating Environment
- TBD

## 3. External Interface Requirements
- APIs / Integrations: Technical consideration: CRUD operations for all major entities

## 4. System Features
### 4.1 Feature
- Description: The system SHALL support event type: Class visits.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.2 Feature
- Description: The system SHALL support event type: Field trips.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.3 Feature
- Description: The system SHALL support event type: Company visits.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.4 Feature
- Description: The system SHALL support event type: Virtual events.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.5 Feature
- Description: The system SHALL support event type: Miscellaneous activities.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.6 Feature
- Description: The system SHALL store event data field: Event type classification.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.7 Feature
- Description: The system SHALL store event data field: Host information.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.8 Feature
- Description: The system SHALL store event data field: Date/time details.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.9 Feature
- Description: The system SHALL store event data field: Location/venue.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.10 Feature
- Description: The system SHALL store event data field: Description and requirements.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.11 Feature
- Description: The system SHALL maintain host profile field: Organization name.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.12 Feature
- Description: The system SHALL maintain host profile field: County location.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.13 Feature
- Description: The system SHALL maintain host profile field: Website URL.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.14 Feature
- Description: The system SHALL maintain host profile field: Industry classification.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.15 Feature
- Description: The system SHALL maintain host profile field: Organization type (Company vs Non-Profit).
- Priority: TBD
- Acceptance Criteria: TBD
### 4.16 Feature
- Description: The system SHALL support request type: School visit requests (companies visiting schools).
- Priority: TBD
- Acceptance Criteria: TBD
### 4.17 Feature
- Description: The system SHALL support request type: Reverse visit requests (schools visiting companies).
- Priority: TBD
- Acceptance Criteria: TBD
### 4.18 Feature
- Description: The system SHALL support request type: Sponsorship requests.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.19 Feature
- Description: The system SHALL provide discovery capability: Location-based event search ("I'm in Westerville, find me something to do").
- Priority: TBD
- Acceptance Criteria: TBD
### 4.20 Feature
- Description: The system SHALL provide discovery capability: Member directory with contact preferences.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.21 Feature
- Description: The system SHALL provide discovery capability: Event filtering by type, location, date.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.22 Feature
- Description: The system SHALL support sponsorship capability: Sponsor profile creation.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.23 Feature
- Description: The system SHALL support sponsorship capability: Sponsorship opportunity matching.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.24 Feature
- Description: The system SHALL support sponsorship capability: Sponsor form completion with option selection.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.25 Feature
- Description: The system SHALL provide email/notification capability: Customizable email templates for different scenarios.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.26 Feature
- Description: The system SHALL provide email/notification capability: Automated teacher notifications for sticker programs.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.27 Feature
- Description: The system SHALL provide email/notification capability: Event reminder system for hosts and participants.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.28 Feature
- Description: The system SHALL provide email/notification capability: Pre-event instruction emails.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.29 Feature
- Description: The system SHALL provide email/notification capability: Follow-up communication templates.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.30 Feature
- Description: The system SHALL provide reporting capability: Daily activity summaries powered by AI.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.31 Feature
- Description: The system SHALL provide reporting capability: Event participation tracking.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.32 Feature
- Description: The system SHALL provide reporting capability: Social media integration (hashtag aggregation).
- Priority: TBD
- Acceptance Criteria: TBD
### 4.33 Feature
- Description: The system SHALL provide reporting capability: Screenshot/media archiving from events.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.34 Feature
- Description: Success Metric: Increased event participation across Ohio
- Priority: TBD
- Acceptance Criteria: TBD
### 4.35 Feature
- Description: Success Metric: Streamlined event coordination process
- Priority: TBD
- Acceptance Criteria: TBD
### 4.36 Feature
- Description: Success Metric: Enhanced teacher engagement with tech companies
- Priority: TBD
- Acceptance Criteria: TBD
### 4.37 Feature
- Description: Success Metric: Improved sponsor-event matching
- Priority: TBD
- Acceptance Criteria: TBD
### 4.38 Feature
- Description: Success Metric: Better tracking and reporting of tech education activities
- Priority: TBD
- Acceptance Criteria: TBD
### 4.39 Feature
- Description: Success Metric: This platform will serve as the foundation for inspiring and coordinating Ohio Tech Day activities while providing administrators with the tools needed to manage the growing network of tech education partnerships across the state.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.40 Feature
- Description: The system SHALL maintain conference data: Year and title.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.41 Feature
- Description: The system SHALL maintain conference data: Theme and description.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.42 Feature
- Description: The system SHALL maintain conference data: Venue and dates (start/end).
- Priority: TBD
- Acceptance Criteria: TBD
### 4.43 Feature
- Description: The system SHALL maintain conference data: Pre-event activities.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.44 Feature
- Description: The system SHALL maintain conference data: During-event activities.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.45 Feature
- Description: The system SHALL maintain conference data: Post-event activities.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.46 Feature
- Description: NFR - Performance: First render within 2.5s on a typical broadband connection.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.47 Feature
- Description: NFR - Accessibility: Page meets WCAG 2.1 AA for color contrast and alt text on images.
- Priority: TBD
- Acceptance Criteria: TBD
### 4.48 Feature
- Description: NFR - Privacy: Do not persist PII beyond recipient name in the client; no server storage by default.
- Priority: TBD
- Acceptance Criteria: TBD

## 5. Nonfunctional Requirements
- Performance / Security / Compliance: The system SHALL support event type: Field trips.

## 6. Other Requirements
- Success Metrics: The system SHALL support event type: Company visits.