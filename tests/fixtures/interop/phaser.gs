import Phaser from "phaser"

var config Phaser.Types.Core.GameConfig = {
  type: Phaser.HEADLESS,
  width: 16,
  height: 16,
  audio: {noAudio: true},
  scene: {
    create: func() {
      document.body.dataset.result = "phaser:" + Phaser.VERSION
    },
  },
}
game := new Phaser.Game(config)
