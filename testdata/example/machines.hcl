variable "suffix" {
  value = "!"
}

machine "laptop" {
  hostname = "laptop"
  use      = ["greeting"]

  ensure "note" {
    text = "inline${var.suffix}"
  }
}

machine "desktop" {
  hostname = "desktop"
  use      = ["greeting"]
}
