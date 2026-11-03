import React, { useState, useRef, useEffect, useMemo } from 'react'
import {
  ArrowUp,
  ArrowDown,
  ArrowUpDown,
  Filter,
  Search,
  CheckSquare,
  Square,
  X,
  RotateCcw,
} from 'lucide-react'

export interface SortConfig {
  key: string
  direction: 'asc' | 'desc'
}

interface Props {
  columnKey: string
  title: string
  sortType?: 'text' | 'number' | 'date'
  currentSort: SortConfig | null
  onSortChange: (sort: SortConfig | null) => void
  uniqueValues: string[]
  valueCounts: Record<string, number>
  selectedValues: string[] | null // null = all selected (no filter active)
  onFilterChange: (selected: string[] | null) => void
  align?: 'left' | 'center' | 'right'
}

export const ExcelColumnHeader: React.FC<Props> = ({
  columnKey,
  title,
  sortType = 'text',
  currentSort,
  onSortChange,
  uniqueValues,
  valueCounts,
  selectedValues,
  onFilterChange,
  align = 'left',
}) => {
  const [isOpen, setIsOpen] = useState(false)
  const [searchValue, setSearchValue] = useState('')
  const popoverRef = useRef<HTMLDivElement>(null)

  // Estado temporal de selección en el menú
  const [tempSelected, setTempSelected] = useState<string[]>(() => {
    return selectedValues ?? uniqueValues
  })

  // Sincronizar tempSelected al abrir el menú
  useEffect(() => {
    if (isOpen) {
      setTempSelected(selectedValues ?? uniqueValues)
      setSearchValue('')
    }
  }, [isOpen, selectedValues, uniqueValues])

  // Cerrar popover al hacer clic fuera
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isOpen])

  const isSorted = currentSort?.key === columnKey
  const sortDir = isSorted ? currentSort?.direction : null
  const isFiltered = selectedValues !== null && selectedValues.length < uniqueValues.length

  // Filtrar valores según el input de búsqueda dentro del popover
  const filteredOptions = useMemo(() => {
    if (!searchValue.trim()) return uniqueValues
    const q = searchValue.toLowerCase().trim()
    return uniqueValues.filter((val) => val.toLowerCase().includes(q))
  }, [uniqueValues, searchValue])

  const allFilteredSelected =
    filteredOptions.length > 0 &&
    filteredOptions.every((v) => tempSelected.includes(v))

  const toggleSelectAll = () => {
    if (allFilteredSelected) {
      // Deseleccionar los visibles
      setTempSelected((prev) => prev.filter((v) => !filteredOptions.includes(v)))
    } else {
      // Seleccionar todos los visibles
      const toAdd = filteredOptions.filter((v) => !tempSelected.includes(v))
      setTempSelected((prev) => [...prev, ...toAdd])
    }
  }

  const toggleOption = (val: string) => {
    setTempSelected((prev) =>
      prev.includes(val) ? prev.filter((v) => v !== val) : [...prev, val]
    )
  }

  const handleApplyFilter = () => {
    if (tempSelected.length === uniqueValues.length || tempSelected.length === 0) {
      onFilterChange(null) // Todos seleccionados o ninguno = sin filtro
    } else {
      onFilterChange(tempSelected)
    }
    setIsOpen(false)
  }

  const handleClearFilter = () => {
    onFilterChange(null)
    setTempSelected(uniqueValues)
    setIsOpen(false)
  }

  const getSortLabels = () => {
    if (sortType === 'number') {
      return {
        asc: 'Ordenar de menor a mayor',
        desc: 'Ordenar de mayor a menor',
      }
    }
    if (sortType === 'date') {
      return {
        asc: 'Ordenar más antiguo a más reciente',
        desc: 'Ordenar más reciente a más antiguo',
      }
    }
    return {
      asc: 'Ordenar de A a Z',
      desc: 'Ordenar de Z a A',
    }
  }

  const sortLabels = getSortLabels()

  return (
    <div
      className={`relative inline-flex items-center gap-1.5 w-full select-none ${
        align === 'center' ? 'justify-center' : align === 'right' ? 'justify-end' : 'justify-start'
      }`}
      ref={popoverRef}
    >
      <span className="truncate">{title}</span>

      {/* Botón de Menú Excel */}
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        title={`Filtro y orden en columna ${title}`}
        className={`p-1 rounded-md transition-all cursor-pointer flex items-center justify-center ${
          isFiltered || isSorted
            ? 'bg-uct-blue-primary text-white shadow-2xs hover:bg-uct-blue-secondary'
            : 'text-slate-400 hover:text-slate-700 hover:bg-slate-200/70'
        }`}
      >
        {isSorted ? (
          sortDir === 'asc' ? (
            <ArrowUp size={12} strokeWidth={2.5} />
          ) : (
            <ArrowDown size={12} strokeWidth={2.5} />
          )
        ) : isFiltered ? (
          <Filter size={11} strokeWidth={2.5} />
        ) : (
          <ArrowUpDown size={11} />
        )}
      </button>

      {/* Menú Desplegable Tipo Excel */}
      {isOpen && (
        <div
          className={`absolute top-full mt-1.5 w-64 bg-white rounded-xl shadow-xl border border-slate-200 z-50 p-3 text-xs text-slate-700 animate-in fade-in zoom-in-95 duration-100 normal-case font-normal text-left ${
            align === 'right' ? 'right-0' : 'left-0'
          }`}
        >
          {/* Cabecera del Popover */}
          <div className="flex items-center justify-between pb-2 border-b border-slate-100">
            <span className="font-bold text-[11px] text-slate-800 truncate">
              {title}
            </span>
            <button
              type="button"
              onClick={() => setIsOpen(false)}
              className="p-1 text-slate-400 hover:text-slate-600 rounded-md hover:bg-slate-100 cursor-pointer"
            >
              <X size={12} />
            </button>
          </div>

          {/* Opciones de Ordenamiento */}
          <div className="py-2 space-y-1 border-b border-slate-100">
            <button
              type="button"
              onClick={() => {
                onSortChange({ key: columnKey, direction: 'asc' })
                setIsOpen(false)
              }}
              className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-left transition-colors cursor-pointer ${
                isSorted && sortDir === 'asc'
                  ? 'bg-uct-blue-primary/10 text-uct-blue-primary font-bold'
                  : 'hover:bg-slate-50 text-slate-700'
              }`}
            >
              <ArrowUp size={13} className="text-slate-500 shrink-0" />
              <span className="truncate">{sortLabels.asc}</span>
            </button>

            <button
              type="button"
              onClick={() => {
                onSortChange({ key: columnKey, direction: 'desc' })
                setIsOpen(false)
              }}
              className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-left transition-colors cursor-pointer ${
                isSorted && sortDir === 'desc'
                  ? 'bg-uct-blue-primary/10 text-uct-blue-primary font-bold'
                  : 'hover:bg-slate-50 text-slate-700'
              }`}
            >
              <ArrowDown size={13} className="text-slate-500 shrink-0" />
              <span className="truncate">{sortLabels.desc}</span>
            </button>

            {isSorted && (
              <button
                type="button"
                onClick={() => {
                  onSortChange(null)
                  setIsOpen(false)
                }}
                className="w-full flex items-center gap-2 px-2 py-1 text-slate-400 hover:text-slate-700 hover:bg-slate-50 rounded-lg text-left transition-colors cursor-pointer text-[11px]"
              >
                <RotateCcw size={11} className="shrink-0" />
                <span>Restablecer orden</span>
              </button>
            )}
          </div>

          {/* Buscador de valores dentro de la columna */}
          <div className="pt-2 pb-1.5">
            <div className="relative">
              <Search
                size={12}
                className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400"
              />
              <input
                type="text"
                value={searchValue}
                onChange={(e) => setSearchValue(e.target.value)}
                placeholder="Buscar valores..."
                className="w-full pl-7 pr-6 py-1 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:border-uct-blue-primary"
              />
              {searchValue && (
                <button
                  type="button"
                  onClick={() => setSearchValue('')}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 cursor-pointer"
                >
                  <X size={11} />
                </button>
              )}
            </div>
          </div>

          {/* Lista de selección de valores tipo Excel */}
          <div className="py-1">
            {/* Casilla Seleccionar Todo */}
            <div
              onClick={toggleSelectAll}
              className="flex items-center gap-2 p-1.5 rounded-md hover:bg-slate-50 cursor-pointer text-slate-800 font-semibold"
            >
              {allFilteredSelected ? (
                <CheckSquare size={14} className="text-uct-blue-primary shrink-0" />
              ) : (
                <Square size={14} className="text-slate-400 shrink-0" />
              )}
              <span className="text-[11px] truncate">
                {searchValue ? '(Seleccionar todos los resultados)' : '(Seleccionar todo)'}
              </span>
            </div>

            {/* Opciones con scroll */}
            <div className="max-h-44 overflow-y-auto space-y-0.5 pr-1 divide-y divide-slate-50">
              {filteredOptions.length === 0 ? (
                <p className="text-[11px] text-slate-400 text-center py-3">
                  No hay coincidencias
                </p>
              ) : (
                filteredOptions.map((val) => {
                  const isChecked = tempSelected.includes(val)
                  const count = valueCounts[val] ?? 0
                  return (
                    <div
                      key={val}
                      onClick={() => toggleOption(val)}
                      className="flex items-center justify-between p-1 rounded-md hover:bg-slate-50 cursor-pointer group"
                    >
                      <div className="flex items-center gap-2 truncate">
                        {isChecked ? (
                          <CheckSquare size={13} className="text-uct-blue-primary shrink-0" />
                        ) : (
                          <Square size={13} className="text-slate-400 shrink-0 group-hover:text-slate-600" />
                        )}
                        <span className="text-[11px] text-slate-700 truncate" title={val}>
                          {val || '(Vacío)'}
                        </span>
                      </div>
                      <span className="text-[10px] text-slate-400 font-mono ml-2 shrink-0">
                        {count}
                      </span>
                    </div>
                  )
                })
              )}
            </div>
          </div>

          {/* Botones de acción inferiores */}
          <div className="pt-2 border-t border-slate-100 flex items-center justify-between gap-2">
            <button
              type="button"
              onClick={handleClearFilter}
              disabled={!isFiltered}
              className="text-[11px] font-semibold text-slate-500 hover:text-slate-800 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
            >
              Limpiar filtro
            </button>

            <button
              type="button"
              onClick={handleApplyFilter}
              className="px-3 py-1 bg-uct-blue-primary hover:bg-uct-blue-secondary text-white font-bold rounded-lg text-xs transition-colors cursor-pointer shadow-2xs"
            >
              Aplicar
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
