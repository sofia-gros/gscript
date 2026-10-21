import { Person as User, twice, label } from "./model.gs"
import defaultTwice from "./model.gs"
import * as model from "./model.gs"
func greet(user User) string { return user.Greet() }
p := User{Name: "Sofia"}
q := new model.Person({Name: "GS"})
console.log(greet(p), q.Greet(), label, twice(21), defaultTwice(2))
