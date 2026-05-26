(function () {
  const workflowByModal = new WeakMap();

  if (window.ModalWorkflow) {
    const OriginalModalWorkflow = window.ModalWorkflow;
    window.ModalWorkflow = function (options) {
      const workflow = OriginalModalWorkflow(options);
      const originalLoadBody = workflow.loadBody;
      workflow.loadBody = function (data) {
        originalLoadBody.call(workflow, data);
        const bodyEl = workflow.body?.[0] || workflow.body;
        if (bodyEl) {
          const modalEl =
            bodyEl.closest?.("[data-chooser-modal]") ||
            bodyEl.closest?.(".modal") ||
            workflow.dialog;
          if (modalEl) {
            workflowByModal.set(modalEl, workflow);
          }
        }
      };
      return workflow;
    };
  }

  function findSearchForm(link) {
    const modal = link.closest("[data-chooser-modal]") || link.closest(".modal");
    if (modal) {
      const form = modal.querySelector("form[data-chooser-modal-search]");
      if (form) {
        return form;
      }
    }
    return document.querySelector("form[data-chooser-modal-search]");
  }

  function findModalRoot(link) {
    return link.closest("[data-chooser-modal]") || link.closest(".modal");
  }

  function getWorkflow(link) {
    const modal = findModalRoot(link);
    if (!modal) {
      return null;
    }
    return workflowByModal.get(modal);
  }

  function navigateTreeChooser(event) {
    const link = event.currentTarget;
    const form = findSearchForm(link);
    if (!form) {
      return;
    }
    const url = link.getAttribute("href");
    if (!url) {
      return;
    }
    event.preventDefault();
    form.querySelector('input[name="parent_pk"]')?.remove();
    form.action = url;
    form.requestSubmit();
  }

  function loadModalUrl(event) {
    const link = event.currentTarget;
    const url = link.getAttribute("href");
    if (!url) {
      return;
    }
    event.preventDefault();
    const workflow = getWorkflow(link);
    if (workflow && typeof workflow.loadUrl === "function") {
      workflow.loadUrl(url);
    }
  }

  function clearParentChoice(event) {
    const button = event.currentTarget;
    const field = document.querySelector(".treebeard-snippet-parent-chooser-input");
    if (field) {
      field.value = "";
      field.dispatchEvent(new Event("change", { bubbles: true }));
    }
    const modal = button.closest("[data-chooser-modal]") || button.closest(".modal");
    if (modal && window.ModalWorkflow && modal.id) {
      window.ModalWorkflow.dismiss(modal.id);
    }
  }

  document.body.addEventListener("click", (event) => {
    const navigate = event.target.closest(".treebeard-snippet-chooser-navigate");
    if (navigate) {
      navigateTreeChooser({ preventDefault: () => event.preventDefault(), currentTarget: navigate });
      return;
    }
    const createLink = event.target.closest(".treebeard-snippet-chooser-create-link");
    if (createLink) {
      loadModalUrl({ preventDefault: () => event.preventDefault(), currentTarget: createLink });
      return;
    }
    const browseLink = event.target.closest(".treebeard-snippet-chooser-browse-link");
    if (browseLink) {
      loadModalUrl({ preventDefault: () => event.preventDefault(), currentTarget: browseLink });
      return;
    }
    const clearRoot = event.target.closest(".treebeard-snippet-chooser-clear-parent");
    if (clearRoot) {
      event.preventDefault();
      clearParentChoice({ currentTarget: clearRoot });
    }
  });
})();
