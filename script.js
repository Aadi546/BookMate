document.addEventListener("DOMContentLoaded", () => {

  const currentPage = window.location.pathname.split("/").pop();
  document.querySelectorAll('#navbar a').forEach(link => {
    const linkPage = link.getAttribute('href');
    if (linkPage === currentPage || (currentPage === "" && linkPage === "index.html")) {
      link.classList.add('active');
    }
  });

 /*card*/
  const featureContainer = document.getElementById("feature-container");
  if (featureContainer) {
    const features = [
      { title: "Easy Book Management", description: "Add and organize your book collection easily." },
      { title: "Personalized Suggestions", description: "Get recommendations based on your interests." },
      { title: "Community Sharing", description: "Share and discover books from other readers." },
      { title: "Works on Any Device", description: "Enjoy BOOKMATE on mobile, tablet, or desktop." }
    ];
    features.forEach(f => {
      const card = document.createElement("div");
      card.className = "feature-card";
      card.innerHTML = `<h3>${f.title}</h3><p>${f.description}</p>`;
      featureContainer.appendChild(card);
    });
  }

  /*localstoring*/
  const bookForm = document.getElementById("bookForm");
  if (bookForm) {
    bookForm.addEventListener("submit", function (e) {
      e.preventDefault();
      const title = document.getElementById("title").value.trim();
      const author = document.getElementById("author").value.trim();
      const price = document.getElementById("price").value.trim();
      const photoInput = document.getElementById("photo");

      if (!title || !author || !price) {
        alert("Please fill all fields!");
        return;
      }
      if (parseFloat(price) < 10) {
        alert("Price must be at least ₹10.");
        return;
      }
      if (photoInput.files.length === 0) {
        alert("Please select a book image.");
        return;
      }

      const reader = new FileReader();
      reader.onload = function () {
        const bookData = { title, author, price, photo: reader.result };
        let books = JSON.parse(localStorage.getItem("books")) || [];
        books.push(bookData);
        localStorage.setItem("books", JSON.stringify(books));
        alert("Book saved successfully!");
        bookForm.reset();
      };
      reader.readAsDataURL(photoInput.files[0]);
    });
  }

/*darkmode*/
  const toggleBtn = document.getElementById("darkModeToggle");
  if (toggleBtn) {
    if (localStorage.getItem("theme") === "dark") {
      document.body.classList.add("dark-mode");
      toggleBtn.textContent = "☀️";
    } else {
      toggleBtn.textContent = "🌙";
    }

    toggleBtn.addEventListener("click", () => {
      document.body.classList.toggle("dark-mode");
      if (document.body.classList.contains("dark-mode")) {
        localStorage.setItem("theme", "dark");
        toggleBtn.textContent = "☀️";
      } else {
        localStorage.setItem("theme", "light");
        toggleBtn.textContent = "🌙";
      }
    });
  }

});
