import { BranchPickerPrimitive } from "@assistant-ui/react";
import { ChevronLeftIcon, ChevronRightIcon } from "lucide-react";
import { Button } from "../ui/Button";
import { Text } from "../ui/Text";

/**
 * Prev/next navigation between alternate branches of a message — created by
 * editing a user message or regenerating an assistant reply. Renders nothing
 * while the message has a single branch.
 */
export function BranchPicker({ className = "" }: { className?: string }) {
  return (
    <BranchPickerPrimitive.Root
      hideWhenSingleBranch
      className={"flex items-center gap-0.5 " + className}
    >
      <BranchPickerPrimitive.Previous asChild>
        <Button variant="icon" size="sm" aria-label="Previous branch">
          <ChevronLeftIcon className="w-3.5 h-3.5" />
        </Button>
      </BranchPickerPrimitive.Previous>
      <Text variant="caption">
        <BranchPickerPrimitive.Number /> / <BranchPickerPrimitive.Count />
      </Text>
      <BranchPickerPrimitive.Next asChild>
        <Button variant="icon" size="sm" aria-label="Next branch">
          <ChevronRightIcon className="w-3.5 h-3.5" />
        </Button>
      </BranchPickerPrimitive.Next>
    </BranchPickerPrimitive.Root>
  );
}
