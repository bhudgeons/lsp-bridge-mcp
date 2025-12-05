package example.services

import example.models.User

/** Validates and analyzes email addresses. */
object EmailValidator {

  /** Analyzes a list of users and returns validation results.
    *
    * @return A ValidationResult containing various email statistics
    */
  def analyzeEmails(users: List[User]): ValidationResult = {
    val (valid, invalid) = users.partition(_.isValidEmail)
    val domains = valid.map(_.email.split("@").last).distinct
    ValidationResult(
      validUsers = valid,
      invalidUsers = invalid,
      uniqueDomains = domains,
      validCount = valid.length,
      invalidCount = invalid.length
    )
  }
}

/** Results from email validation analysis. */
case class ValidationResult(
    validUsers: List[User],
    invalidUsers: List[User],
    uniqueDomains: List[String],
    validCount: Int,
    invalidCount: Int
)
