package example

import example.models.User
import example.services.{UserService, EmailValidator}

object App {
  def main(args: Array[String]): Unit = {
    val service = new UserService()

    // Create some users (some with invalid emails for demo)
    val usersToCreate = List(
      ("Alice", "alice@example.com"),
      ("Bob", "bob@example.com"),
      ("Charlie", "charlie-no-at-sign"),  // Invalid email
      ("Diana", "diana@company.org")
    )

    usersToCreate.foreach { case (name, email) =>
      User.create(name, email) match {
        case Right(user) =>
          service.addUser(user)
          println(s"Created user: ${user.greeting}")
        case Left(error) =>
          println(s"Failed to create $name: $error")
      }
    }

    // List all users
    println("\nAll users:")
    service.getAllUsers.foreach { user =>
      println(s"  - ${user.name} (${user.email})")
    }

    // Analyze emails
    val analysis = EmailValidator.analyzeEmails(service.getAllUsers)
    println(s"\nEmail analysis complete.")
  }
}
