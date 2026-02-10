const input = document.getElementById('filesInput');
const fileList = document.getElementById('selectedFiles');
const label = document.getElementById('fileDropLabel');

if (input) {
  input.addEventListener('change', () => {
    fileList.innerHTML = '';

    if (!input.files.length) {
      label.textContent = 'Choose files or drag them here';
      return;
    }

    label.textContent = `${input.files.length} file(s) selected`;
    Array.from(input.files).forEach((file) => {
      const li = document.createElement('li');
      li.textContent = `• ${file.name}`;
      fileList.appendChild(li);
    });
  });
}
