# Backlog for A Book Store

## Epics
### Epic 1: Online Book Browsing
- **Feature 1.1:** Browse Books by Category
  - **User Story 1.1.1:** As a User, I want to browse books by category so that I can find books that interest me.
    - **Acceptance Criteria:**
      - Given I am on the homepage, when I select a category, then I should see a list of books in that category.
      - Given I am viewing books, when I click on a book, then I should see the book details.
      - Given I am viewing books, when I filter by author, then I should see books by that author.
      - Given I am viewing books, when I sort by price, then I should see books sorted by price.

### Epic 2: Online Purchasing
- **Feature 2.1:** Purchase Books
  - **User Story 2.1.1:** As a User, I want to purchase books online so that I can receive them at home.
    - **Acceptance Criteria:**
      - Given I have selected a book, when I click on 'Buy Now', then I should be taken to the checkout page.
      - Given I am on the checkout page, when I enter my payment details, then I should be able to complete my purchase.
      - Given I have completed my purchase, when I check my email, then I should receive a confirmation email.
      - Given I am on the checkout page, when I enter invalid payment details, then I should see an error message.

### Epic 3: Inventory Management
- **Feature 3.1:** Manage Inventory
  - **User Story 3.1.1:** As an Admin, I want to manage inventory so that I can keep track of stock levels.
    - **Acceptance Criteria:**
      - Given I am logged in as an Admin, when I access the inventory management interface, then I should see a list of all books.
      - Given I am viewing the inventory, when I add a new book, then it should appear in the inventory list.
      - Given I am viewing the inventory, when I update a book's stock level, then the updated level should be reflected.
      - Given I am viewing the inventory, when I delete a book, then it should no longer appear in the inventory list.

### Epic 4: User Reviews
- **Feature 4.1:** Submit Reviews
  - **User Story 4.1.1:** As a User, I want to submit reviews for purchased books so that I can share my feedback.
    - **Acceptance Criteria:**
      - Given I have purchased a book, when I navigate to the book page, then I should see an option to submit a review.
      - Given I am submitting a review, when I enter my feedback and rating, then I should be able to submit it.
      - Given I have submitted a review, when I refresh the page, then I should see my review displayed.
      - Given I am submitting a review, when I enter invalid data, then I should see an error message.

## Definitions of Ready (DoR)
- User stories must have clear acceptance criteria.
- User stories must be estimated by the team.
- User stories must be prioritized in the backlog.

## Definitions of Done (DoD)
- Code is written and reviewed.
- Tests are written and pass.
- Documentation is updated.