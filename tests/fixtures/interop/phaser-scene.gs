import Phaser from "phaser"

type GameScene struct extends Phaser.Scene {
  Speed number = 240
}

func (g GameScene) constructor() {
  super("gs-main")
}

func (g GameScene) create() {
  document.body.dataset.result = "phaser:" + Phaser.VERSION
}

var config Phaser.Types.Core.GameConfig = {
  type: Phaser.HEADLESS,
  width: 16,
  height: 16,
  audio: {noAudio: true},
  scene: GameScene,
}
game := new Phaser.Game(config)
