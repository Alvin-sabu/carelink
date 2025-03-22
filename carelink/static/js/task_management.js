// Task Management Module
const TaskManager = {
    // Get CSRF token from cookie
    getCsrfToken: function() {
        const name = 'csrftoken';
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    },

    // Handle API responses
    handleResponse: async function(response) {
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'An error occurred');
        }
        return data;
    },

    // Mark task for review
    markForReview: async function(taskId) {
        try {
            const response = await fetch(`/task/${taskId}/mark-review/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': this.getCsrfToken(),
                    'Content-Type': 'application/json',
                },
            });
            const result = await this.handleResponse(response);
            this.updateTaskDisplay(taskId, 'PENDING_REVIEW');
            return result;
        } catch (error) {
            console.error('Error marking task for review:', error);
            throw error;
        }
    },

    // Approve task completion
    approveTask: async function(taskId) {
        try {
            const response = await fetch(`/task/${taskId}/approve/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': this.getCsrfToken(),
                    'Content-Type': 'application/json',
                },
            });
            const result = await this.handleResponse(response);
            this.updateTaskDisplay(taskId, 'COMPLETED');
            return result;
        } catch (error) {
            console.error('Error approving task:', error);
            throw error;
        }
    },

    // Get task details
    getTask: async function(taskId) {
        try {
            const response = await fetch(`/task/${taskId}/`);
            return await this.handleResponse(response);
        } catch (error) {
            console.error('Error getting task details:', error);
            throw error;
        }
    },

    // Edit task
    editTask: async function(taskId, taskData) {
        try {
            const response = await fetch(`/task/${taskId}/edit/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': this.getCsrfToken(),
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(taskData)
            });
            const result = await this.handleResponse(response);
            this.updateTaskDisplay(taskId, taskData.status, taskData);
            return result;
        } catch (error) {
            console.error('Error editing task:', error);
            throw error;
        }
    },

    // Delete task
    deleteTask: async function(taskId) {
        if (!confirm('Are you sure you want to delete this task?')) {
            return;
        }
        try {
            const response = await fetch(`/task/${taskId}/delete/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': this.getCsrfToken(),
                    'Content-Type': 'application/json',
                },
            });
            const result = await this.handleResponse(response);
            document.querySelector(`#task-${taskId}`).remove();
            return result;
        } catch (error) {
            console.error('Error deleting task:', error);
            throw error;
        }
    },

    // Update task display in the UI
    updateTaskDisplay: function(taskId, status, taskData = null) {
        const taskElement = document.querySelector(`#task-${taskId}`);
        if (!taskElement) return;

        // Update status badge
        const statusBadge = taskElement.querySelector('.status-badge');
        if (statusBadge) {
            statusBadge.textContent = status.replace('_', ' ');
            statusBadge.className = `status-badge badge ${this.getStatusClass(status)}`;
        }

        // Update task details if provided
        if (taskData) {
            const titleElement = taskElement.querySelector('.task-title');
            if (titleElement) titleElement.textContent = taskData.title;

            const descriptionElement = taskElement.querySelector('.task-description');
            if (descriptionElement) descriptionElement.textContent = taskData.description;

            const dueDateElement = taskElement.querySelector('.task-due-date');
            if (dueDateElement) dueDateElement.textContent = taskData.due_date;

            const priorityBadge = taskElement.querySelector('.priority-badge');
            if (priorityBadge) {
                priorityBadge.textContent = taskData.priority;
                priorityBadge.className = `priority-badge badge ${this.getPriorityClass(taskData.priority)}`;
            }
        }

        // Update action buttons based on status
        this.updateActionButtons(taskElement, status);
    },

    // Get appropriate CSS class for status badge
    getStatusClass: function(status) {
        const statusClasses = {
            'PENDING': 'bg-warning',
            'PENDING_REVIEW': 'bg-info',
            'COMPLETED': 'bg-success'
        };
        return statusClasses[status] || 'bg-secondary';
    },

    // Get appropriate CSS class for priority badge
    getPriorityClass: function(priority) {
        const priorityClasses = {
            'HIGH': 'bg-danger',
            'MEDIUM': 'bg-warning',
            'LOW': 'bg-info'
        };
        return priorityClasses[priority] || 'bg-secondary';
    },

    // Update action buttons based on task status
    updateActionButtons: function(taskElement, status) {
        const actionButtons = taskElement.querySelector('.task-actions');
        if (!actionButtons) return;

        const isStaff = document.body.dataset.isStaff === 'true';
        const markReviewBtn = actionButtons.querySelector('.mark-review-btn');
        const approveBtn = actionButtons.querySelector('.approve-btn');
        const editBtn = actionButtons.querySelector('.edit-btn');
        const deleteBtn = actionButtons.querySelector('.delete-btn');

        if (status === 'PENDING') {
            if (markReviewBtn) markReviewBtn.style.display = '';
            if (approveBtn) approveBtn.style.display = 'none';
            if (editBtn) editBtn.style.display = '';
            if (deleteBtn) deleteBtn.style.display = '';
        } else if (status === 'PENDING_REVIEW') {
            if (markReviewBtn) markReviewBtn.style.display = 'none';
            if (approveBtn) approveBtn.style.display = isStaff ? '' : 'none';
            if (editBtn) editBtn.style.display = isStaff ? '' : 'none';
            if (deleteBtn) deleteBtn.style.display = isStaff ? '' : 'none';
        } else if (status === 'COMPLETED') {
            if (markReviewBtn) markReviewBtn.style.display = 'none';
            if (approveBtn) approveBtn.style.display = 'none';
            if (editBtn) editBtn.style.display = 'none';
            if (deleteBtn) deleteBtn.style.display = isStaff ? '' : 'none';
        }
    }
};

// Export the module
window.TaskManager = TaskManager; 