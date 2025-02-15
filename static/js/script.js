let logData = [];
let txtFileContent = null;
let currentFileStats = { files: [] };
let currentSort = { field: null, direction: 'asc' };
let currentSearchType = 'all';
let telegramSearchResponse = null;
let isTelegramResults = false;

// DOM Elements
const dropZone = document.getElementById('dropZone');
const queryInput = document.getElementById('queryInput');
const modal = document.getElementById('fileStatsModal');
const fileStatsLoader = document.getElementById('fileStatsLoader');
const totalLinesCount = document.getElementById('totalLinesCount');
const searchTypeBtn = document.getElementById('searchTypeBtn');
const searchTypeMenu = document.getElementById('searchTypeMenu');
const currentSearchTypeText = document.getElementById('currentSearchType');

// Button click handlers
document.getElementById('queryBtn').onclick = handleSearch;
document.getElementById('exportCsvBtn').onclick = () => exportToCSV(logData);
document.getElementById('exportJsonBtn').onclick = () => exportToJSON(logData);
document.getElementById('exportUniquePasswordsBtn').onclick = () => exportUniquePasswords(logData);
document.getElementById('exportUniqueEmailsBtn').onclick = () => exportUniqueEmails(logData);
document.getElementById('showFileStatsBtn').onclick = showFileStats;
document.getElementById('refreshStatsBtn').onclick = fetchFileStats;
document.getElementById('resetBtn').onclick = resetApplication;
document.querySelector('.close').onclick = closeModal;

// Modal handlers
window.onclick = (event) => {
    if (event.target === modal) closeModal();
};

// Sort handlers
document.querySelectorAll('.sort-btn').forEach(btn => {
    btn.addEventListener('click', () => sortFiles(btn.dataset.sort));
});

searchTypeBtn.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    searchTypeMenu.classList.toggle('show');
});

// Handle search type selection
document.querySelectorAll('.search-type-item').forEach(item => {
    item.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        const value = item.dataset.value;
        currentSearchType = value;
        currentSearchTypeText.textContent = value.toUpperCase();
        searchTypeMenu.classList.remove('show');
    });
});

// Close dropdown when clicking outside
document.addEventListener('click', (e) => {
    if (!searchTypeBtn.contains(e.target) && !searchTypeMenu.contains(e.target)) {
        searchTypeMenu.classList.remove('show');
    }
});

dropZone.addEventListener('click', (e) => {
    if (searchTypeBtn.contains(e.target) || searchTypeMenu.contains(e.target)) {
        e.stopPropagation();
    }
});

// Drag and drop handlers
['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, preventDefaults, false);
    document.body.addEventListener(eventName, preventDefaults, false);
});

['dragenter', 'dragover'].forEach(eventName => {
    dropZone.addEventListener(eventName, highlight, false);
});

['dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, unhighlight, false);
});

dropZone.addEventListener('drop', handleDrop, false);

// File handling functions
function handleDrop(e) {
    const dt = e.dataTransfer;
    const file = dt.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
        try {
            if (file.name.endsWith('.json')) {
                logData = JSON.parse(event.target.result);
                populateTable(logData);
            } else if (file.name.endsWith('.csv')) {
                logData = parseCSV(event.target.result);
                populateTable(logData);
            } else if (file.name.endsWith('.txt')) {
                txtFileContent = event.target.result;
                queryInput.value = `Loaded file: ${file.name}`;
                queryInput.disabled = true;
            }
        } catch (error) {
            console.error('Error parsing file:', error);
        }
    };

    if (file.name.match(/\.(json|csv|txt)$/)) {
        reader.readAsText(file);
    }
}

function parseCSV(csv) {
    const lines = csv.split('\n');
    const headers = lines[0].split(',').map(header =>
        header.trim().toLowerCase().replace(/["']/g, '')
    );

    return lines.slice(1)
        .map(line => {
            if (!line.trim()) return null;
            const values = line.split(',').map(value =>
                value.trim().replace(/["']/g, '')
            );
            const obj = {};
            headers.forEach((header, i) => {
                obj[header] = values[i] || '';
            });
            return obj;
        })
        .filter(item => item !== null);
}

// UI update functions
function populateTable(data) {
    const tbody = document.getElementById('logsTableBody');
    const noResultsMessage = document.getElementById('noResultsMessage');
    const importSection = document.getElementById('importSection');
    tbody.innerHTML = '';

    if (data.length === 0) {
        noResultsMessage.classList.remove('hidden');
        importSection.classList.add('hidden');
        isTelegramResults = false;
    } else {
        noResultsMessage.classList.add('hidden');
        if (isTelegramResults) {
            importSection.classList.remove('hidden');
        } else {
            importSection.classList.add('hidden');
        }
    }

    data.forEach(log => {
        const row = document.createElement('tr');
        row.className = 'border-b border-gray-800 hover:bg-gray-900';

        const redactedDomain = truncateText(log.domain, 30);
        const redactedUri = truncateText(log.uri, 30);
        const redactedEmail = truncateText(log.email, 30);
        const redactedPassword = truncateText(log.password, 30);

        row.innerHTML = `
            <td class="py-3 px-6">
                <div class="domain-cell">
                    <img src="https://www.google.com/s2/favicons?domain=${encodeURIComponent(log.domain)}&sz=48"
                         alt="${redactedDomain} favicon" class="w-6 h-6 mr-3">
                    <div class="table-cell-content">${redactedDomain}</div>
                </div>
            </td>
            <td class="py-3 px-6">
                <div class="table-cell-content text-gray-300">${redactedUri || "-"}</div>
            </td>
            <td class="py-3 px-6">
                <div class="table-cell-content text-gray-300">${redactedEmail}</div>
            </td>
            <td class="py-3 px-6">
                <div class="table-cell-content text-gray-300">${redactedPassword}</div>
            </td>
        `;
        tbody.appendChild(row);
    });
}

document.getElementById('searchTelegramBtn').addEventListener('click', async () => {
    const loader = document.getElementById('loader');
    loader.classList.remove('hidden');

    try {
        const response = await fetch('/api/logs/search-telegram/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                query: txtFileContent ? txtFileContent.split('\n').filter(line => line.trim()).join('|') : queryInput.value,
                field: currentSearchType,
                bulk: !!txtFileContent
            })
        });

        telegramSearchResponse = await response.json();

        // Set flag for Telegram results
        isTelegramResults = true;

        // Update UI with Telegram results
        document.getElementById('telegramResultCount').textContent = telegramSearchResponse.count;

        // Show results in table
        populateTable(telegramSearchResponse.results);
    } catch (error) {
        console.error('Error searching Telegram:', error);
    } finally {
        loader.classList.add('hidden');
    }
});

document.getElementById('importResultsBtn').addEventListener('click', async () => {
    if (!telegramSearchResponse?.file_path) return;

    const loader = document.getElementById('loader');
    loader.classList.remove('hidden');

    try {
        const response = await fetch(`/api/logs/import/?file_path=${encodeURIComponent(telegramSearchResponse.file_path)}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });

        if (response.ok) {
            handleSearch();
            document.getElementById('importSection').classList.add('hidden');
        }
    } catch (error) {
        console.error('Error importing results:', error);
    } finally {
        loader.classList.add('hidden');
    }
});

// Utility functions
function truncateText(text, maxLength) {
    return text.length > maxLength ? text.slice(0, maxLength) + '...' : text;
}

function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
}

function highlight() {
    dropZone.classList.add('drag-over');
}

function unhighlight() {
    dropZone.classList.remove('drag-over');
}

function closeModal() {
    modal.style.display = 'none';
}

function showFileStats() {
    modal.style.display = 'block';
    fetchFileStats();
}

// File statistics functions
async function fetchFileStats() {
    fileStatsLoader.classList.remove('hidden');
    try {
        const response = await fetch('/api/logs/files/');
        currentFileStats = await response.json();
        updateFileStatsTable();
    } catch (error) {
        console.error('Error fetching file stats:', error);
    } finally {
        fileStatsLoader.classList.add('hidden');
    }
}

function sortFiles(field) {
    if (currentSort.field === field) {
        currentSort.direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
    } else {
        currentSort.field = field;
        currentSort.direction = 'asc';
    }

    // Update sort icons and active states
    document.querySelectorAll('.sort-btn i').forEach(icon => {
        icon.className = 'fas fa-sort';
    });
    document.querySelectorAll('.sort-btn').forEach(btn => {
        btn.classList.remove('active');
    });

    const currentButton = document.querySelector(`.sort-btn[data-sort="${field}"]`);
    currentButton.classList.add('active');
    currentButton.querySelector('i').className =
        `fas fa-sort-${currentSort.direction === 'asc' ? 'up' : 'down'}`;

    updateFileStatsTable();
}

function updateFileStatsTable() {
    const tbody = document.getElementById('fileStatsTableBody');
    const files = [...currentFileStats.files];

    if (currentSort.field) {
        files.sort((a, b) => {
            let comparison = 0;
            if (currentSort.field === 'timestamp') {
                comparison = new Date(a.creation_time) - new Date(b.creation_time);
            } else if (currentSort.field === 'lines') {
                comparison = a.line_count - b.line_count;
            }
            return currentSort.direction === 'asc' ? comparison : -comparison;
        });
    }

    tbody.innerHTML = '';
    let total = 0;

    files.forEach(file => {
        total += file.line_count;
        const row = document.createElement('tr');
        row.className = 'border-b border-gray-800 hover:bg-gray-900';
        row.innerHTML = `
            <td class="py-3 px-6">
                <div class="flex items-center">
                    <i class="fas fa-file-text mr-3 text-gray-500"></i>
                    <div class="text-white">${file.filename}</div>
                </div>
            </td>
            <td class="py-3 px-6 text-gray-300">
                ${new Date(file.creation_time).toLocaleString()}
            </td>
            <td class="py-3 px-6 text-gray-300">
                ${file.line_count.toLocaleString()}
            </td>
        `;
        tbody.appendChild(row);
    });

    totalLinesCount.textContent = total.toLocaleString();
}

// Search and reset functions
async function handleSearch() {
    const loader = document.getElementById('loader');
    loader.classList.remove('hidden');
    isTelegramResults = false;

    try {
        let response;
        if (txtFileContent) {
            const processedContent = txtFileContent.split('\n')
                .filter(line => line.trim())
                .join('|');
            response = await fetch('/api/logs/search/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    query: processedContent,
                    field: currentSearchType,
                    bulk: true
                })
            });
        } else {
            response = await fetch('/api/logs/search/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    query: queryInput.value,
                    field: currentSearchType,
                    bulk: false
                })
            });
        }

        logData = await response.json();
        populateTable(logData);
    } catch (error) {
        console.error('Error fetching data:', error);
    } finally {
        loader.classList.add('hidden');
    }
}

function resetApplication() {
    txtFileContent = null;
    queryInput.value = '';
    queryInput.disabled = false;
    logData = [];
    document.getElementById('logsTableBody').innerHTML = '';
}

// Export functions
function exportToCSV(data) {
    const headers = ['Domain', 'URI', 'Email', 'Password'];
    const csvRows = [
        headers.join(','),
        ...data.map(row =>
            headers.map(header => {
                const value = row[header.toLowerCase()] || '';
                const escaped = value.toString().replace(/"/g, '\\"');
                return `"${escaped}"`;
            }).join(',')
        )
    ];

    downloadFile(csvRows.join('\n'), 'logs.csv', 'text/csv');
}

function exportToJSON(data) {
    const jsonString = JSON.stringify(data, null, 2);
    downloadFile(jsonString, 'logs.json', 'application/json');
}

function exportUniquePasswords(data) {
    const uniquePasswords = [...new Set(data.map(item => item.password))];
    const jsonString = JSON.stringify(uniquePasswords, null, 2);
    downloadFile(jsonString, 'unique_passwords.json', 'application/json');
}

function exportUniqueEmails(data) {
    const uniqueEmails = [...new Set(data.map(item => item.email))];
    const jsonString = JSON.stringify(uniqueEmails, null, 2);
    downloadFile(jsonString, 'unique_emails.json', 'application/json');
}

function downloadFile(content, fileName, contentType) {
    const blob = new Blob([content], { type: contentType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = fileName;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}