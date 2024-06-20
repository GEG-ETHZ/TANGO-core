# TANGO Software Development Guidelines for GitHub

## Overview

This document contains development guidelines for managing bug fixes and implementing new features in TANGO. It's purpose is to promote a smooth and efficient development workflow among all developers. Everyone is invited to contribute to these guidelines, and following them will help maintain a high-quality codebase.

## Bug Reporting and Fixing

Below are the steps to follow when reporting a new bug and fixing it in TANGO.

### Reporting a New Bug

1. **Create a GitHub Issue**: Whenever a new bug is found, create a new GitHub Issue. This will help track the bug and its resolution.
2. **Provide Details**: In the issue, provide detailed information about the bug. This should include:
   - A clear description of the bug.
   - Steps to reproduce the bug.
   - Expected behavior.
   - Actual behavior.
   - Any relevant screenshots or logs if possible.

Example:

**Title**: TANGO fails when simulating with native reservoir model.
**Description**: The input script below configures TANGO to use its native reservoir model. When running with porosity value 0.123, TANGO fails.

`<<< YAML SCRIPT HERE >>>`

**Expected Behavior**: The calculation should not fail with porosity 0.123 when it succeeds with 0.12 and 0.13.

**Actual Behavior**: The simulation fails with message "`<<< SOME ERROR MESSAGE HERE >>>`".

**Screenshots/Logs**: `[Attach if available]`

### Fixing the Bug

1. **Create a Branch**: Create a new branch from the **main branch** for the bug fix. It is recommended to name the branch using the following naming convention: `developer-name/short-description-issue-number`, for example, `allanleal/fixing-division-by-zero-issue-123`.
2. **Develop the Fix**: Implement the necessary code changes to fix the bug.
3. **Write Tests**: Whenever possible, develop sufficient tests to ensure the bug does not reappear in the future.
4. **Create a Pull Request (PR)**: Once the fix is implemented and tested, create a PR to merge the changes into the main branch. Ensure the PR:
   - References the GitHub Issue where the bug was reported.
   - Provides a clear description of the changes made.

5. **Code Review**: The code changes will be reviewed. Make any necessary adjustments based on feedback.
6. **Merge the PR**: Once approved, the PR will be merged into the main branch.
7. **Release**: After merging, produce a new release for TANGO with incremented version number (e.g., v1.2.3 becomes v1.2.4).

## Implementing New Features

### Reporting a New Feature
1. **Create a GitHub Issue**: Before developing a new feature, create a GitHub Issue detailing what is going to be developed.
2. **Provide Details**: In the issue, include:
   - A clear description of the feature.
   - The motivation for the feature.
   - Any relevant mockups or diagrams.

Example:
```
**Feature**: Add user authentication system

**Description**: Implement a user authentication system allowing users to sign up, log in, and log out.

**Motivation**: Enhances security by restricting access to certain features to authenticated users only.

**Mockups/Diagrams**: [Attach if available]
```

### Developing the Feature
1. **Create a Branch**: Create a new branch from the main branch for the feature development.
2. **Develop the Feature**: Implement the necessary code changes for the new feature.
3. **Create a Pull Request (PR)**: Once the feature is implemented and tested, create a PR to merge the changes into the main branch. Ensure the PR:
   - Mentions the GitHub Issue where the feature was originally discussed.
   - Provides a clear description of the changes made.

4. **Code Review**: The code changes will be reviewed. Make any necessary adjustments based on feedback.
5. **Merge the PR**: Once approved, the PR will be merged into the main branch.
6. **Release**: After merging, produce a new release for TANGO.

## Testing

### Using Pytest
1. **Write Tests**: All new features and bug fixes should include appropriate tests using `pytest`.
2. **Run Tests**: Ensure that all tests pass before creating a Pull Request. Run the tests with:
   ```
   pytest
   ```
3. **Continuous Integration**: Our CI pipeline will run the tests automatically on each PR. Ensure all tests pass before merging.

## Documentation

### Using Sphinx
1. **Write Documentation**: All new features and significant changes should be documented using Sphinx. Update the `.rst` files accordingly.
2. **Build Documentation**: Ensure the documentation builds correctly by running:
   ```
   make html
   ```
3. **Review Documentation**: Documentation will be reviewed as part of the PR process. Ensure it is clear and comprehensive.

## Summary
By following these guidelines for bug reporting, bug fixing, feature implementation, testing, and documentation, we can maintain a structured and efficient development process for TANGO. This helps ensure high-quality code and smooth project progression.
