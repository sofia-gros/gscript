export type Person struct {
  Name string
}
func (p Person) Greet() string {
  return "Hello, " + p.Name
}
export func twice(n int) int { return n * 2 }
export const label string = "answer"
export default twice
