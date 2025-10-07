# Backlog for Bookstore Mimicking Amazon's Original Platform

## Epics
### Epic 1: User Account Management
- **Feature 1.1:** User Registration
- **Feature 1.2:** Guest Checkout

### Epic 2: Book Browsing and Search
- **Feature 2.1:** Browse Categories
- **Feature 2.2:** Read Reviews

### Epic 3: Shopping Cart Management
- **Feature 3.1:** Manage Shopping Cart
- **Feature 3.2:** Checkout Process

## User Stories
### User Story 1: User Registration
- **As a** user, **I want** to create an account **so that** I can manage my purchases.
- **Acceptance Criteria:**
  - Given I am on the registration page, when I fill in my details and submit, then my account should be created successfully.
  - Given I have an existing account, when I try to register again, then I should see an error message.
  - Given I am on the registration page, when I leave required fields empty, then I should see validation messages.
  - Given I have created an account, when I log in, then I should be redirected to my account dashboard.

### User Story 2: Guest Checkout
- **As a** user, **I want** to purchase books without creating an account **so that** I can complete my purchase quickly.
- **Acceptance Criteria:**
  - Given I have added books to my cart, when I choose guest checkout, then I should be able to proceed without creating an account.
  - Given I am on the guest checkout page, when I fill in my details and submit, then my order should be processed successfully.
  - Given I am a guest user, when I try to access my order history, then I should see a message indicating that I need an account.
  - Given I have completed a guest checkout, when I return to the site, then I should not have an account created automatically.

### User Story 3: Browse Categories
- **As a** user, **I want** to browse categories of books **so that** I can find books of interest easily.
- **Acceptance Criteria:**
  - Given I am on the homepage, when I click on a category, then I should see a list of books in that category.
  - Given I am viewing a category, when I filter by author, then I should see only books by that author.
  - Given I am on the category page, when I sort by price, then I should see the books sorted accordingly.
  - Given I am browsing, when I click on a book, then I should be taken to the book details page.

### User Story 4: Read Reviews
- **As a** user, **I want** to read reviews of books **so that** I can make informed purchasing decisions.
- **Acceptance Criteria:**
  - Given I am on a book details page, when I scroll down, then I should see a list of reviews for that book.
  - Given I am viewing reviews, when I click on a review, then I should see the full review details.
  - Given I am on the book details page, when there are no reviews, then I should see a message indicating that there are no reviews yet.
  - Given I am a logged-in user, when I submit a review, then it should be added to the list of reviews for that book.

### User Story 5: Manage Shopping Cart
- **As a** user, **I want** to manage my shopping cart **so that** I can add or remove books before checkout.
- **Acceptance Criteria:**
  - Given I have added books to my cart, when I view my cart, then I should see all the selected books.
  - Given I am viewing my cart, when I remove a book, then it should no longer appear in my cart.
  - Given I am viewing my cart, when I change the quantity of a book, then the total price should update accordingly.
  - Given I am ready to checkout, when I click on the checkout button, then I should be taken to the checkout page.

## Definitions
- **Definition of Ready (DoR):** User stories must have clear acceptance criteria and be estimated.
- **Definition of Done (DoD):** User stories are considered done when they meet acceptance criteria, are tested, and are deployed to production.