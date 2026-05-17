(function () {
  function findSearchForm(link) {
    const modal = link.closest("[data-chooser-modal]");
    if (modal) {
      const form = modal.querySelector("form[data-chooser-modal-search]");
      if (form) {
        return form;
      }
    }
    return document.querySelector("form[data-chooser-modal-search]");
  }

  function navigateTreeChooser(event) {
    const link = event.currentTarget;
    const form = findSearchForm(link);
    if (!form) {
      return;
    }
    event.preventDefault();
    let parentInput = form.querySelector('input[name="parent_pk"]');
    if (!parentInput) {
      parentInput = document.createElement("input");
      parentInput.type = "hidden";
      parentInput.name = "parent_pk";
      form.appendChild(parentInput);
    }
    parentInput.value = link.dataset.parentPk || "";
    form.requestSubmit();
  }

  function clearParentChoice(event) {
    const button = event.currentTarget;
    const field = document.querySelector(".treebeard-snippet-parent-chooser-input");
    if (field) {
      field.value = "";
      field.dispatchEvent(new Event("change", { bubbles: true }));
    }
    const modal = button.closest("[data-chooser-modal]");
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
    const clearRoot = event.target.closest(".treebeard-snippet-chooser-clear-parent");
    if (clearRoot) {
      event.preventDefault();
      clearParentChoice({ currentTarget: clearRoot });
    }
  });
})();
