// game.js
export function startGame(containerId) {
    const config = {
        type: Phaser.AUTO,
        width: 800,
        height: 600,
        parent: containerId,
        backgroundColor: '#2d2d2d',
        scene: {
            preload: preload,
            create: create,
            update: update
        }
    };

    const game = new Phaser.Game(config);

    function preload () {
        this.load.image('sky', 'https://labs.phaser.io/assets/skies/sky2.png');
        this.load.image('star', 'https://labs.phaser.io/assets/sprites/star.png');
    }

    let star;

    function create () {
        this.add.image(400, 300, 'sky');

        star = this.add.image(400, 100, 'star');
        star.setInteractive();
        this.input.on('pointerdown', function (pointer) {
            star.x = pointer.x;
            star.y = pointer.y;
        });

        this.add.text(10, 10, 'Drag the star!', { font: '32px Arial', fill: '#ffffff' });
    }

    function update () {
        // Simple rotation
        star.rotation += 0.01;
    }
}
