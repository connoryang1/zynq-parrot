# Ordinary-header equivalent of the maintained01444fa PCH overlay; no cache.
VK_PCH_I_FAST = -include $(VM_PREFIX)__pch.h
VK_PCH_I_SLOW = -include $(VM_PREFIX)__pch.h
$(VM_PREFIX)__pch.h.fast.gch: ;
$(VM_PREFIX)__pch.h.slow.gch: ;
