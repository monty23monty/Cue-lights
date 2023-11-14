var socket = io();
      // Event handler for successful connection
      socket.on("connect", function () {
        console.log("Connected to server.");
      });
      const questionTextElement = document.getElementById("questionText");
      const userAnswerElement = document.getElementById("inp");
      const submitAnswerBtn = document.getElementById("buttons");
      const userId = "{{ user_id }}";

      // Join a room
      console.log("Joining room:", "{{ room.code }}"); // Add this line for debugging
      socket.emit("join_room", {
        room_code: "{{ room.code }}",
        room_id: "{{ room.id }}", // Room ID is obtained from the server-side Flask variable
      });
      // Event handler to redirect to ready_check.html
      socket.on("redirect_to_ready_check", function (data) {
        window.location.href = data.url;
      });
      // Event handler to update user status in real-time
      socket.on("update_user_status_not_ready", function (data) {
        console.log("Received update_user_status_not_ready event:", data); // Added for debugging

        // Update the list of users who are not ready
        const userStatusListNotReady = document.getElementById(
          "userStatusListNotReady"
        );
        userStatusListNotReady.innerHTML = "";
        for (const user of data.users) {
          const userStatusElement = document.createElement("li");
          userStatusElement.textContent = user.username;
          userStatusListNotReady.appendChild(userStatusElement);
        }
      });

      socket.on("update_user_status_ready", function (data) {
        console.log("Received update_user_status_ready event:", data); // Added for debugging

        // Update the list of users who are ready
        const userStatusListReady = document.getElementById(
          "userStatusListReady"
        );
        userStatusListReady.innerHTML = "";
        for (const user of data.users) {
          const userStatusElement = document.createElement("li");
          userStatusElement.textContent = user.username;
          userStatusListReady.appendChild(userStatusElement);
        }
      });

      // Event handler for disconnection
      socket.on("disconnect", function () {
        console.log("Disconnected from server.");
      });

      // Event handler for updates to the list of connected users
      socket.on("connected_users_update", function (data) {
        console.log("Received connected_users_update event:", data); // Added for debugging

        console.log("Updated list of connected users:", data.users);
      });
      // Event handler to update user readiness lists based on the broadcasted status using the data in app.py
      socket.on("update_user_status", function (data) {
        console.log("Received update_user_status event:", data); // Added for debugging

        // Update the list of users who are not ready
        const userStatusListNotReady = document.getElementById(
          "userStatusListNotReady"
        );
        userStatusListNotReady.innerHTML = "";
        for (const user of data.users_not_ready) {
          const userStatusElement = document.createElement("li");
          userStatusElement.textContent = user.username;
          userStatusListNotReady.appendChild(userStatusElement);
        }

        // Update the list of users who are ready
        const userStatusListReady = document.getElementById(
          "userStatusListReady"
        );
        userStatusListReady.innerHTML = "";
        for (const user of data.users_ready) {
          const userStatusElement = document.createElement("li");
          userStatusElement.textContent = user.username;
          userStatusListReady.appendChild(userStatusElement);
        }
    });
    // go
    const btnGo = document.getElementById("btnGo");

btnGo.addEventListener("click", function () {
  socket.emit("start_show", {
    user_id: userId,
    room_id: "{{ room.id }}",
  });
});

      socket.on("error", function (data) {
        console.log("Error:", data.message);
      });
      //event handler for redirecting to show page
      socket.on("start_show", function (data) {
        window.location.href = data.url;
      });