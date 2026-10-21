type Entity interface {
  get() int
}

type Container<T> struct {
  Value T
}

func (c Container<T>) get() T {
  return c.Value
}

type State enum {
  Idle
  Active
}

func show(value Entity?) int {
  return value?.get() ?? 0
}

var item Entity = Container<int>{Value: 42}
switch State.Active {
case State.Active:
  console.log(show(item))
default:
  console.log(show(nil))
}
