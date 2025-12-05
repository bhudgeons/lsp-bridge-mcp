package example.services

import example.models.User
import scala.collection.mutable

/** Service for managing users.
  *
  * Provides CRUD operations for User entities.
  */
class UserService {
  private val users = mutable.Map[Long, User]()

  def addUser(user: User): Unit = {
    users(user.id) = user
  }

  def getUser(id: Long): Option[User] = {
    users.get(id)
  }

  def findByEmail(email: String): Option[User] = {
    users.values.find(_.email == email)
  }

  def getAllUsers: List[User] = {
    users.values.toList
  }

  def deleteUser(id: Long): Boolean = {
    users.remove(id).isDefined
  }

  def updateEmail(id: Long, newEmail: String): Option[User] = {
    users.get(id).map { user =>
      val updated = user.copy(email = newEmail)
      users(id) = updated
      updated
    }
  }
}
