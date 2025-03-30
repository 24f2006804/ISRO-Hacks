// Utility function to show alerts
function showAlert(message, type = 'success') {
    const alertContainer = document.querySelector('.alert-container') || (() => {
        const div = document.createElement('div');
        div.className = 'alert-container';
        document.body.appendChild(div);
        return div;
    })();

    const alert = document.createElement('div');
    alert.className = `alert alert-${type} alert-dismissible fade show`;
    alert.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    alertContainer.appendChild(alert);

    setTimeout(() => alert.remove(), 5000);
}

// Handle file uploads for CSV imports
function handleFileUpload(file, endpoint) {
    const formData = new FormData();
    formData.append('file', file);

    return axios.post(endpoint, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
    })
    .then(response => {
        if (response.data.success) {
            showAlert('File imported successfully');
            return response.data;
        } else {
            throw new Error(response.data.message || 'Import failed');
        }
    })
    .catch(error => {
        showAlert(error.message, 'danger');
        throw error;
    });
}

// Initialize drag and drop zones
document.addEventListener('DOMContentLoaded', () => {
    const dropZones = document.querySelectorAll('.drag-drop-zone');
    
    dropZones.forEach(zone => {
        zone.addEventListener('dragover', (e) => {
            e.preventDefault();
            zone.classList.add('dragover');
        });

        zone.addEventListener('dragleave', () => {
            zone.classList.remove('dragover');
        });

        zone.addEventListener('drop', (e) => {
            e.preventDefault();
            zone.classList.remove('dragover');
            
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                const endpoint = zone.dataset.endpoint;
                handleFileUpload(files[0], endpoint);
            }
        });
    });
});

// Format dates for display
function formatDate(dateString) {
    return new Date(dateString).toLocaleString();
}

// Generic function to load and display data
async function loadData(endpoint, containerId, template) {
    try {
        const response = await axios.get(endpoint);
        const container = document.getElementById(containerId);
        if (container && response.data) {
            container.innerHTML = template(response.data);
        }
    } catch (error) {
        showAlert(error.message, 'danger');
    }
}

// Search functionality
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Handle search input
const searchHandler = debounce((value) => {
    if (!value) return;
    
    axios.get(`/api/search?itemId=${value}`)
        .then(response => {
            if (response.data.found) {
                const searchResults = document.getElementById('searchResults');
                if (searchResults) {
                    // Display item details
                    const item = response.data.item;
                    searchResults.innerHTML = `
                        <div class="card">
                            <div class="card-body">
                                <h5 class="card-title">${item.name}</h5>
                                <p class="card-text">
                                    ID: ${item.itemId}<br>
                                    Location: ${item.containerId || 'Not placed'}<br>
                                    Status: ${item.isWaste ? 'Waste' : 'Active'}
                                </p>
                            </div>
                        </div>
                    `;
                }
            }
        })
        .catch(error => showAlert(error.message, 'danger'));
}, 300);