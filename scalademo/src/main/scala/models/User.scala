package example.models

import java.time.LocalDateTime

/** Represents a user in the system.
  *
  * @param id Unique identifier
  * @param name Display name
  * @param email Email address
  * @param createdAt When the user was created
  */
case class User(
    id: Long,
    name: String,
    email: String,
    createdAt: LocalDateTime = LocalDateTime.now()
) {
  def isValidEmail: Boolean = email.contains("@") && email.contains(".")

  def greeting: String = s"Hello, $name!"
}

object User {
  def create(name: String, email: String): Either[String, User] = {
    if (name.isEmpty) Left("Name cannot be empty")
    else if (!email.contains("@")) Left("Invalid email format")
    else Right(User(System.currentTimeMillis(), name, email))
  }
}
