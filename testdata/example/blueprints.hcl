blueprint "greeting" {
  description = "Say hello to whoever is logged in."

  ensure "note" {
    text = "hello ${env.USER}"
  }
}
