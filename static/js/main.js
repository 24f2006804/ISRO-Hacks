// Utility functions
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
async function handleFileUpload(file, endpoint) {
    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await axios.post(endpoint, formData, {
            headers: { 'Content-Type': 'multipart/form-data' }
        });

        if (response.data.success) {
            showAlert('File imported successfully');
            
            // After successful import, trigger placement if both containers and items are loaded
            const containersLoaded = await checkContainersExist();
            const itemsLoaded = await checkItemsExist();
            
            if (containersLoaded && itemsLoaded) {
                await triggerPlacement();
                await loadContainerVisualizations();
            }
            
            return response.data;
        } else {
            throw new Error(response.data.message || 'Import failed');
        }
    } catch (error) {
        showAlert(error.message, 'danger');
        throw error;
    }
}

async function checkContainersExist() {
    try {
        const response = await axios.get('/api/containers/check');
        return response.data.containersExist;
    } catch (error) {
        console.error('Error checking containers:', error);
        return false;
    }
}

async function checkItemsExist() {
    try {
        const response = await axios.get('/api/items/check');
        return response.data.itemsExist;
    } catch (error) {
        console.error('Error checking items:', error);
        return false;
    }
}

async function triggerPlacement() {
    try {
        const response = await axios.post('/api/placement/optimize');
        if (response.data.success) {
            showAlert('Items placed successfully');
            return true;
        }
        return false;
    } catch (error) {
        showAlert('Error placing items: ' + error.message, 'danger');
        return false;
    }
}

// Initialize drag and drop zones
document.addEventListener('DOMContentLoaded', () => {
    initializeDragAndDrop();
    initializeContainerVisualizations();
    initializeSimulationEffects();
});

function initializeDragAndDrop() {
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

        const input = zone.querySelector('input[type="file"]');
        zone.addEventListener('click', () => input.click());
        input.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                handleFileUpload(e.target.files[0], zone.dataset.endpoint);
            }
        });
    });
}

// Enhanced container visualization
function initializeContainerVisualizations() {
    const containers = document.querySelectorAll('.container-visualization');
    containers.forEach(container => {
        initializeThreeJS(container);
        updateContainerVisualization(container);
    });
}

function initializeThreeJS(containerElement) {
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(75, containerElement.clientWidth / containerElement.clientHeight, 0.1, 1000);
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    
    renderer.setSize(containerElement.clientWidth, containerElement.clientHeight);
    containerElement.appendChild(renderer.domElement);
    
    // Add ambient light
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
    scene.add(ambientLight);
    
    // Add directional light
    const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
    dirLight.position.set(5, 5, 5);
    scene.add(dirLight);
    
    // Store Three.js objects in the container element
    containerElement.threeData = { scene, camera, renderer };
    
    // Set initial camera position
    camera.position.set(200, 200, 200);
    camera.lookAt(0, 0, 0);
    
    // Add OrbitControls
    const controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    containerElement.threeData.controls = controls;
    
    // Start animation loop
    animate(containerElement);
}

function animate(containerElement) {
    const { scene, camera, renderer, controls } = containerElement.threeData;
    
    function render() {
        requestAnimationFrame(render);
        controls.update();
        renderer.render(scene, camera);
    }
    
    render();
}

async function updateContainerVisualization(containerElement) {
    const containerId = containerElement.dataset.containerId;
    const { scene } = containerElement.threeData;

    try {
        // Clear existing items
        while (scene.children.length > 0) {
            scene.remove(scene.children[0]);
        }

        // Get container data
        const containerResponse = await axios.get(`/api/containers/${containerId}`);
        const container = containerResponse.data;

        // Create container mesh
        const containerGeometry = new THREE.BoxGeometry(container.width, container.height, container.depth);
        const containerMaterial = new THREE.MeshPhongMaterial({ 
            color: 0x808080,
            transparent: true,
            opacity: 0.2,
            wireframe: true
        });
        const containerMesh = new THREE.Mesh(containerGeometry, containerMaterial);
        scene.add(containerMesh);

        // Get items in container
        const itemsResponse = await axios.get(`/api/containers/${containerId}/items`);
        const items = itemsResponse.data;

        // Add items to scene
        items.forEach(item => {
            // Validate item dimensions against container dimensions
            if (
                item.width > container.width ||
                item.depth > container.depth ||
                item.height > container.height
            ) {
                console.warn(`Item ${item.itemId} exceeds container dimensions and will not be visualized.`);
                return;
            }

            const itemGeometry = new THREE.BoxGeometry(item.width, item.height, item.depth);
            const itemMaterial = new THREE.MeshPhongMaterial({ 
                color: getPriorityColor(item.priority),
                transparent: true,
                opacity: 0.8
            });
            const itemMesh = new THREE.Mesh(itemGeometry, itemMaterial);

            // Position item
            const position = item.position;
            itemMesh.position.set(
                position.startCoordinates.width + (item.width / 2),
                position.startCoordinates.height + (item.height / 2),
                position.startCoordinates.depth + (item.depth / 2)
            );

            scene.add(itemMesh);
        });

    } catch (error) {
        console.error('Error updating container visualization:', error);
    }
}

async function loadContainerVisualizations() {
    const containers = document.querySelectorAll('.container-visualization');
    for (const container of containers) {
        await updateContainerVisualization(container);
    }
}

function getPriorityColor(priority) {
    if (priority >= 90) return 0xff0000; // Red for high priority
    if (priority >= 70) return 0xffa500; // Orange for medium priority
    return 0x00ff00; // Green for low priority
}

function onItemHover(event) {
    const item = event.target.userData;
    showItemTooltip(item);
}

// Simulation effects
function initializeSimulationEffects() {
    const simulationContainer = document.getElementById('simulationContainer');
    if (simulationContainer) {
        simulationContainer.classList.add('simulation-day');
    }
}

function simulateTimePassage(days) {
    return new Promise((resolve) => {
        const progressBar = document.createElement('div');
        progressBar.className = 'progress-bar';
        document.getElementById('simulationProgress').appendChild(progressBar);

        let currentDay = 0;
        const interval = setInterval(() => {
            if (currentDay >= days) {
                clearInterval(interval);
                progressBar.remove();
                resolve();
                return;
            }

            currentDay++;
            const progress = (currentDay / days) * 100;
            progressBar.style.width = `${progress}%`;
            
            // Trigger day/night cycle
            document.getElementById('simulationContainer').classList.toggle('simulation-day');
        }, 1000); // 1 second per day
    });
}

// Format dates consistently
function formatDate(dateString) {
    return new Date(dateString).toLocaleString();
}

// Calculate days until expiry
function getDaysUntilExpiry(expiryDate) {
    if (!expiryDate) return Infinity;
    const now = new Date();
    const expiry = new Date(expiryDate);
    return Math.ceil((expiry - now) / (1000 * 60 * 60 * 24));
}

// Generic data loading with template
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

// Debounced search handler
const searchHandler = debounce((value) => {
    if (!value) return;
    
    axios.get(`/api/search?itemId=${value}`)
        .then(response => {
            if (response.data.found) {
                const searchResults = document.getElementById('searchResults');
                if (searchResults) {
                    const item = response.data.item;
                    searchResults.innerHTML = `
                        <div class="card">
                            <div class="card-body">
                                <h5 class="card-title">${item.name}</h5>
                                <p class="card-text">
                                    ID: ${item.itemId}<br>
                                    Location: ${item.containerId || 'Not placed'}<br>
                                    Status: ${item.isWaste ? 'Waste' : 'Active'}<br>
                                    Priority: ${item.priority}<br>
                                    Expiry: ${item.expiryDate ? formatDate(item.expiryDate) : 'N/A'}
                                </p>
                                ${item.retrievalSteps ? `
                                    <div class="mt-3">
                                        <h6>Retrieval Steps:</h6>
                                        <ol>
                                            ${item.retrievalSteps.map(step => 
                                                `<li>${step.action}: ${step.itemName}</li>`
                                            ).join('')}
                                        </ol>
                                    </div>
                                ` : ''}
                            </div>
                        </div>
                    `;
                }
            }
        })
        .catch(error => showAlert(error.message, 'danger'));
}, 300);

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