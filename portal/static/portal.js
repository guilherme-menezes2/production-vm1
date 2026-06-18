(function () {
  function onlyDigits(value) {
    return (value || "").replace(/\D/g, "");
  }

  function isValidCpf(value) {
    var cpf = onlyDigits(value);
    var sum;
    var digit;
    var i;

    if (cpf.length !== 11 || /^(\d)\1{10}$/.test(cpf)) {
      return false;
    }

    sum = 0;
    for (i = 0; i < 9; i += 1) {
      sum += Number(cpf.charAt(i)) * (10 - i);
    }
    digit = (sum * 10) % 11;
    if (digit === 10) {
      digit = 0;
    }
    if (digit !== Number(cpf.charAt(9))) {
      return false;
    }

    sum = 0;
    for (i = 0; i < 10; i += 1) {
      sum += Number(cpf.charAt(i)) * (11 - i);
    }
    digit = (sum * 10) % 11;
    if (digit === 10) {
      digit = 0;
    }
    return digit === Number(cpf.charAt(10));
  }

  function formatCpf(value) {
    var digits = onlyDigits(value).slice(0, 11);
    if (digits.length > 9) {
      return digits.replace(/(\d{3})(\d{3})(\d{3})(\d{0,2})/, "$1.$2.$3-$4");
    }
    if (digits.length > 6) {
      return digits.replace(/(\d{3})(\d{3})(\d{0,3})/, "$1.$2.$3");
    }
    if (digits.length > 3) {
      return digits.replace(/(\d{3})(\d{0,3})/, "$1.$2");
    }
    return digits;
  }

  function setCpfState(input, valid, showMessage) {
    var form = input.form;
    var error = form ? form.querySelector("[data-cpf-error]") : null;
    var message = valid ? "" : "Informe um CPF valido.";

    input.setCustomValidity(message);
    input.classList.toggle("is-invalid", !valid && showMessage);
    input.setAttribute("aria-invalid", valid ? "false" : "true");
    if (error) {
      error.hidden = valid || !showMessage;
      error.textContent = message;
    }
  }

  function validateCpfInput(input, showMessage) {
    var digits = onlyDigits(input.value);
    var valid = digits.length === 11 && isValidCpf(digits);

    if (!digits.length) {
      input.setCustomValidity("");
      input.classList.remove("is-invalid");
      input.setAttribute("aria-invalid", "false");
      return false;
    }

    setCpfState(input, valid, showMessage);
    return valid;
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-validate-cpf]").forEach(function (cpfInput) {
      var form = cpfInput.form;
      if (!form) {
        return;
      }

      cpfInput.value = formatCpf(cpfInput.value);
      validateCpfInput(cpfInput, false);

      cpfInput.addEventListener("input", function () {
        cpfInput.value = formatCpf(cpfInput.value);
        validateCpfInput(cpfInput, false);
      });

      cpfInput.addEventListener("blur", function () {
        validateCpfInput(cpfInput, true);
      });

      form.addEventListener("submit", function (event) {
        if (!validateCpfInput(cpfInput, true)) {
          event.preventDefault();
          cpfInput.focus();
        }
      });
    });
  });
})();
