const socket = io();
let mySymbol = null;
let roomId = null;
let myTurn = false;
let soloMode = false;
const BOARD_N = 16;

const boardEl = document.getElementById('board');
const statusEl = document.getElementById('status');
const menu = document.getElementById('menu');
const gameArea = document.getElementById('game-area');
const turnStatus = document.getElementById('turn-status');
const afterGame = document.getElementById('after-game');
const homeBtn = document.getElementById('home-btn'); // ✅ nút duy nhất
const timerEl = document.getElementById('timer');

/* === Biến đếm giờ === */
let timerInterval = null;
let timeLeft = 30;

/* === Tạo bảng trống === */
function createEmptyBoard() {
    return Array.from({ length: BOARD_N }, () => Array(BOARD_N).fill(''));
}

/* === Vẽ bàn cờ === */
function drawBoard(board, winner_positions = [], lastMove = null) {
    boardEl.innerHTML = '';
    const winSet = new Set(winner_positions.map(p => `${p[0]},${p[1]}`));

    board.forEach((row, i) => {
        row.forEach((cell, j) => {
            const div = document.createElement('div');
            div.classList.add('cell');

            // tô màu X (đỏ), O (xanh)
            if (cell === 'X') div.style.color = '#e53935';
            else if (cell === 'O') div.style.color = '#1e88e5';

            if (winSet.has(`${i},${j}`)) div.classList.add('win');
            if (lastMove && lastMove[0] === i && lastMove[1] === j) div.classList.add('last');

            div.textContent = cell;

            div.onclick = () => {
                if (myTurn && cell === '') {
                    socket.emit('make_move', { room: roomId, row: i, col: j });
                }
            };

            boardEl.appendChild(div);
        });
    });
}

/* === Bộ đếm thời gian === */
function startTimer() {
    clearInterval(timerInterval);
    timeLeft = 30;
    updateTimerText();

    timerInterval = setInterval(() => {
        timeLeft--;
        updateTimerText();

        if (timeLeft <= 0) {
            clearInterval(timerInterval);
            myTurn = false;
            turnStatus.textContent = "⏰ Hết giờ! Bạn đã thua!";
            socket.emit('timeout', { room: roomId });
        }
    }, 1000);
}

function stopTimer() {
    clearInterval(timerInterval);
    timerEl.textContent = '';
}

function updateTimerText() {
    timerEl.textContent = myTurn ? `⏱ Còn lại: ${timeLeft}s` : '';
}

/* === Kết nối socket === */
socket.on('connected', () => {
    statusEl.textContent = '✅ Kết nối thành công. Chọn chế độ để bắt đầu!';
});

/* === Tìm đối thủ hoặc chơi 1 mình === */
document.getElementById('find').onclick = () => {
    soloMode = false;
    socket.emit('find_room', { solo: false });
};

document.getElementById('solo').onclick = () => {
    soloMode = true;
    socket.emit('find_room', { solo: true });
};

/* === Đang chờ người chơi khác === */
socket.on('waiting', data => {
    statusEl.textContent = data.msg;
});

/* === Khi vào phòng thành công === */
socket.on('room_joined', data => {
    roomId = data.room;
    mySymbol = data.symbol;
    menu.style.display = 'none';
    gameArea.style.display = 'block';
    afterGame.style.display = 'none';
    statusEl.textContent = `🎮 Vào phòng ${roomId}. Bạn là ${mySymbol}`;
});

/* === Khi bắt đầu ván mới === */
socket.on('start_game', data => {
    myTurn = (data.turn === mySymbol);
    afterGame.style.display = 'none';
    drawBoard(createEmptyBoard());
    stopTimer();
    if (myTurn) startTimer();
    turnStatus.textContent = myTurn ? "🟢 Đến lượt bạn!" : "🕐 Chờ đối thủ...";
});

/* === Cập nhật trạng thái bàn cờ === */
socket.on('state_update', data => {
    const { board, finished, winner, winner_positions = [], turn } = data;
    drawBoard(board, winner_positions);

    if (finished) {
        stopTimer();
        afterGame.style.display = 'block';

        if (winner === 'draw') {
            turnStatus.textContent = "😐 Hòa!";
        } else if (winner === mySymbol) {
            turnStatus.textContent = "🎉 Bạn thắng!";
        } else if (winner === 'O' && soloMode) {
            turnStatus.textContent = "🤖 Máy thắng!";
        } else {
            turnStatus.textContent = "😭 Bạn thua!";
        }
    } else {
        myTurn = (turn === mySymbol);
        stopTimer();
        if (myTurn) startTimer();
        turnStatus.textContent = myTurn ? "🟢 Đến lượt bạn!" : "🕐 Chờ đối thủ...";
    }
});



/* === Nút Trang chủ duy nhất === */
homeBtn.onclick = () => {
    if (confirm("⚠️ Bạn có chắc muốn thoát ván hiện tại không?")) {
        stopTimer();
        menu.style.display = 'block';
        gameArea.style.display = 'none';
        afterGame.style.display = 'none';
        mySymbol = null;
        roomId = null;
        myTurn = false;
        boardEl.innerHTML = '';
        turnStatus.textContent = '';
        statusEl.textContent = '🏠 Đã quay lại menu chính.';
    }
};
