import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  Box, 
  Container, 
  Typography, 
  Grid, 
  Card, 
  CardContent, 
  CardMedia, 
  CardActionArea,
  Button,
  TextField,
  MenuItem,
  FormControl,
  InputLabel,
  Select,
  Chip,
  Divider,
  Paper,
  Slider,
  OutlinedInput,
  Checkbox,
  ListItemText,
  IconButton,
  useTheme,
  alpha,
  CircularProgress,
  Pagination,
  Stack
} from '@mui/material';
import { 
  DirectionsCar, 
  Search, 
  LocationOn, 
  Person, 
  LocalOffer, 
  Phone, 
  FilterList, 
  Sort, 
  CalendarToday, 
  ColorLens, 
  LocalGasStation, 
  Speed,
  Clear,
  ArrowUpward,
  ArrowDownward,
  Settings 
} from '@mui/icons-material';
import { styled } from '@mui/system';
import { fetchCarListings } from '../api'; // Updated import name
import { useAuth } from '../context/AuthContext';

// Styled components for better UI
const StyledFilterPaper = styled(Paper)(({ theme }) => ({
  padding: theme?.spacing?.(3) || '24px',
  marginBottom: theme?.spacing?.(3) || '24px',
  borderRadius: theme?.shape?.borderRadius || '4px',
  boxShadow: '0 2px 10px rgba(0,0,0,0.08)',
  background: theme?.palette?.background?.paper 
    ? `linear-gradient(145deg, ${theme.palette.background.paper} 0%, ${alpha(theme.palette.primary.light, 0.05)} 100%)`
    : 'linear-gradient(145deg, #ffffff 0%, rgba(25, 118, 210, 0.05) 100%)',
}));

const ListingCard = styled(Card)(({ theme }) => ({
  display: 'flex',
  flexDirection: 'column',
  height: '100%',
  transition: 'transform 0.3s ease, box-shadow 0.3s ease',
  borderRadius: theme?.spacing?.(1) || '8px',
  overflow: 'hidden',
  boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
  '&:hover': {
    transform: 'translateY(-5px)',
    boxShadow: '0 12px 20px rgba(0,0,0,0.15)',
  },
}));

const ListingInfoChip = styled(Chip)(({ theme, color }) => ({
  margin: theme?.spacing?.(0.5) || '4px',
  backgroundColor: color ? alpha(color, 0.1) : (theme?.palette?.primary?.main ? alpha(theme.palette.primary.main, 0.1) : 'rgba(25, 118, 210, 0.1)'),
  color: color || (theme?.palette?.primary?.main || '#1976d2'),
  border: 'none',
  fontWeight: 500,
  '& .MuiChip-icon': {
    color: 'inherit',
  },
}));

const HeaderTypography = styled(Typography)(({ theme }) => ({
  fontWeight: 600,
  position: 'relative',
  paddingLeft: theme?.spacing?.(2) || '16px',
  marginBottom: theme?.spacing?.(3) || '24px',
  '&:before': {
    content: '""',
    position: 'absolute',
    left: 0,
    top: '50%',
    transform: 'translateY(-50%)',
    width: 4,
    height: '70%',
    backgroundColor: theme?.palette?.primary?.main || '#1976d2',
    borderRadius: 4,
  },
}));

// Mock car data from most makes and models
const carData = {
  "Alfa Romeo": ["156", "Giulia", "Giulietta", "Mito"],
  "Audi": ["A1", "A3", "A4", "A5", "A6", "A7", "A8", "Q2", "Q3", "Q5", "Q7", "Q8"],
  "BMW": ["1 Series", "2 Series", "3 Series", "4 Series", "5 Series", "7 Series", "X1", "X3", "X5", "X6"],
  "Chevrolet": ["Aveo", "Camaro", "Captiva", "Cruze", "Malibu", "Spark"],
  "Citroen": ["C3", "C4", "C5", "DS3", "DS4", "DS5"],
  "Fiat": ["500", "Punto", "Tipo"],
  "Ford": ["EcoSport", "Fiesta", "Focus", "Kuga", "Mustang"],
  "Honda": ["Accord", "Civic", "CR-V", "Jazz"],
  "Hyundai": ["Accent", "Elantra", "i10", "i20", "i30", "Tucson"],
  "Jeep": ["Cherokee", "Compass", "Grand Cherokee", "Renegade", "Wrangler"],
  "Kia": ["Ceed", "Cerato", "Picanto", "Rio", "Sorento", "Sportage"],
  "Mazda": ["2", "3", "6", "CX-3", "CX-5", "MX-5"],
  "Mercedes-Benz": ["A-Class", "C-Class", "E-Class", "GLA", "GLC", "S-Class"],
  "Mitsubishi": ["ASX", "Lancer", "Outlander", "Pajero"],
  "Nissan": ["Juke", "Micra", "Qashqai", "X-Trail"],
  "Opel": ["Astra", "Corsa", "Insignia", "Mokka"],
  "Peugeot": ["208", "308", "3008", "508"],
  "Renault": ["Captur", "Clio", "Duster", "Megane"],
  "Skoda": ["Fabia", "Kodiaq", "Octavia", "Superb"],
  "Suzuki": ["Baleno", "Jimny", "Swift", "Vitara"],
  "Toyota": ["Auris", "Avensis", "Corolla", "RAV4", "Yaris"],
  "Volkswagen": ["Golf", "Passat", "Polo", "Tiguan", "Touareg"]
};

const bodyTypeOptions = [
  "SEDAN",
  "COUPE",
  "SPORTS CAR",
  "HATCHBACK",
  "CONVERTIBLE",
  "SUV",
  "MINIVAN",
  "PICKUP TRUCK",
  "STATION WAGON"
];

const colorOptions = [
  "Red", "Blue", "Green", "Black", "White", "Silver", "Gray", "Yellow", "Orange", "Purple", "Brown", "Gold", "Pink"
];

const fuelTypeOptions = [
  "Benzine", "Diesel", "Electric", "Hybrid", "Natural Gas"
];

const locationOptions = [
  "Cairo", "Alexandria", "Giza", "Luxor", "Aswan"
];

const conditionOptions = [
  "New", "Used"
];

const transmissionOptions = [
  "manual", "automatic"
];

// Add this at the top - a hook to persist and track the user ID
const useUserIdTracking = () => {
  const { isAuthenticated, user, loading } = useAuth();
  const [currentUserId, setCurrentUserId] = useState(null);

  // Store user ID in session storage when authenticated
  useEffect(() => {
    if (!loading && isAuthenticated && user) {
      const userId = user.user_id || user._id;
      if (userId) {
        setCurrentUserId(userId);
        // Store in session storage to persist during refresh
        sessionStorage.setItem('marketplace_user_id', userId);
        console.log('User ID stored for filtering:', userId);
      }
    } else if (!loading && !isAuthenticated) {
      // Clear stored ID when not authenticated
      setCurrentUserId(null);
      sessionStorage.removeItem('marketplace_user_id');
    } else if (!loading && isAuthenticated && !currentUserId) {
      // Attempt to restore from session storage if not in state yet
      const storedId = sessionStorage.getItem('marketplace_user_id');
      if (storedId) {
        setCurrentUserId(storedId);
        console.log('User ID restored from session storage:', storedId);
      }
    }
  }, [isAuthenticated, user, loading, currentUserId]);

  return { currentUserId, isLoadingUser: loading };
};

const CarMarketplace = () => {
  const theme = useTheme();
  const navigate = useNavigate();
  const { isAuthenticated, user, loading: authLoading } = useAuth();
  const { currentUserId, isLoadingUser } = useUserIdTracking();
  
  // State for listings and loading
  const [listings, setListings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  // Pagination state
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const itemsPerPage = 12;
  
  // Filter states
  const [filters, setFilters] = useState({
    make: '',
    model: '',
    bodyType: '',
    condition: '',
    minYear: 2000,
    maxYear: new Date().getFullYear(),
    minPrice: '',
    maxPrice: '',
    location: '',
    fuelType: '',
    transmissionType: '',
    color: [],
    sortBy: 'newest',
    search: ''
  });
  
  // Models available for selected make
  const [models, setModels] = useState([]);
  
  // Price range state
  const [priceRange, setPriceRange] = useState([0, 5000000]);
  
  // Filter visibility
  const [showFilters, setShowFilters] = useState(false);
  
  // Set models when make changes
  useEffect(() => {
    if (filters.make) {
      setModels(carData[filters.make] || []);
      setFilters(prev => ({...prev, model: ''}));
    } else {
      setModels([]);
    }
  }, [filters.make]);
  
  // Fetch listings when filters change
  useEffect(() => {
    // Skip fetching until auth state is resolved
    if (isLoadingUser) {
      console.log('Waiting for user authentication state to resolve...');
      return;
    }
    
    const fetchListings = async () => {
      setLoading(true);
      setError(null);
      
      try {
        // Prepare filter parameters
        const filterParams = {
          page,
          limit: itemsPerPage * 2, // Request more items to handle client-side filtering
          ...filters,
          // Convert price range to min/max values if set
          minPrice: priceRange[0] > 0 ? priceRange[0] : undefined,
          maxPrice: priceRange[1] < 5000000 ? priceRange[1] : undefined,
          // Convert color array to string if needed
          color: filters.color.length > 0 ? filters.color : undefined,
        };
        
        // Add user ID to exclude their own listings if authenticated
        // Use both session storage and auth context for redundancy
        const userIdToExclude = currentUserId || 
                              (isAuthenticated && user ? (user.user_id || user._id) : null) ||
                              sessionStorage.getItem('marketplace_user_id');
        
        if (userIdToExclude) {
          filterParams.exclude_user_id = userIdToExclude;
          console.log(`Excluding user's own listings with ID: ${userIdToExclude}`);
        }
        
        console.log("Fetching listings with params:", filterParams);
        const response = await fetchCarListings(filterParams); // Updated function call
        
        // Handle the actual response format from our backend
        if (response && response.listings) {
          // Apply client-side filtering as double verification
          let filteredListings = [...response.listings];
          
          if (userIdToExclude) {
            const initialCount = filteredListings.length;
            filteredListings = filteredListings.filter(listing => {
              // Skip listings without owner_id
              if (!listing.owner_id) return true;
              
              // Normalize and compare owner IDs
              const ownerIdStr = String(listing.owner_id).trim();
              const userIdStr = String(userIdToExclude).trim();
              
              // Debug owner IDs on refresh to help catch issues
              if (ownerIdStr === userIdStr) {
                console.warn(`Found listing that should have been filtered: ${listing.title} (${listing._id})`);
                console.warn(`Owner ID: "${ownerIdStr}", User ID: "${userIdStr}"`);
              }
              
              return ownerIdStr !== userIdStr;
            });
            
            const removedCount = initialCount - filteredListings.length;
            if (removedCount > 0) {
              console.log(`Filtered out ${removedCount} user's own listings client-side`);
            }
          }
          
          // Calculate real pagination based on filtered results
          const totalItemCount = response.pagination?.total || filteredListings.length;
          const adjustedTotalPages = Math.max(1, Math.ceil(totalItemCount / itemsPerPage));
          
          // Combine smaller pages if necessary to make sure we have 12 items per page
          if (filteredListings.length < itemsPerPage && page < adjustedTotalPages) {
            // We need to fetch more items
            console.log(`Page ${page} has fewer than ${itemsPerPage} items (${filteredListings.length}), fetching more...`);
            
            // Get items from next page
            const nextPageParams = {
              ...filterParams,
              page: page + 1,
            };
            
            try {
              const additionalResponse = await fetchCarListings(nextPageParams); // Updated function call
              if (additionalResponse && additionalResponse.listings) {
                // Apply the same filtering
                let additionalFilteredListings = [...additionalResponse.listings];
                
                if (userIdToExclude) {
                  additionalFilteredListings = additionalFilteredListings.filter(listing => {
                    if (!listing.owner_id) return true;
                    return String(listing.owner_id).trim() !== String(userIdToExclude).trim();
                  });
                }
                
                // Combine listings (up to itemsPerPage total)
                const combinedListings = [
                  ...filteredListings,
                  ...additionalFilteredListings.slice(0, itemsPerPage - filteredListings.length)
                ];
                
                console.log(`Added ${combinedListings.length - filteredListings.length} items from next page`);
                filteredListings = combinedListings;
              }
            } catch (additionalErr) {
              console.error('Error fetching additional listings:', additionalErr);
            }
          }
          
          // Ensure we have the right number of items per page
          const finalListings = filteredListings.slice(0, itemsPerPage);
          
          console.log(`Showing ${finalListings.length} listings on page ${page} of ${adjustedTotalPages}`);
          
          setListings(finalListings);
          setTotalPages(adjustedTotalPages);
        } else {
          setListings([]);
          setTotalPages(1);
        }
      } catch (err) {
        console.error('Error fetching listings:', err);
        setError('Failed to load car listings. Please try again later.');
        setListings([]);
      } finally {
        setLoading(false);
      }
    };
    
    fetchListings();
  }, [filters, page, priceRange, isAuthenticated, user, currentUserId, isLoadingUser]);
  
  // Handle filter changes
  const handleFilterChange = (event) => {
    const { name, value } = event.target;
    setFilters(prev => ({...prev, [name]: value}));
    setPage(1); // Reset to first page when filters change
  };
  
  // Handle price range change
  const handlePriceRangeChange = (event, newValue) => {
    setPriceRange(newValue);
  };
  
  // Handle color selection (multiple)
  const handleColorChange = (event) => {
    const { value } = event.target;
    setFilters(prev => ({...prev, color: typeof value === 'string' ? value.split(',') : value}));
    setPage(1);
  };
  
  // Reset all filters
  const handleResetFilters = () => {
    setFilters({
      make: '',
      model: '',
      bodyType: '',
      condition: '',
      minYear: 2000,
      maxYear: new Date().getFullYear(),
      minPrice: '',
      maxPrice: '',
      location: '',
      fuelType: '',
      transmissionType: '',
      color: [],
      sortBy: 'newest',
      search: ''
    });
    setPriceRange([0, 5000000]);
    setPage(1);
  };
  
  // Handle view listing details
  const handleViewListing = (listingId) => {
    // Navigate to the correct route that matches our detail component's URL pattern
    navigate(`/car/${listingId}`);
  };
  
  // Handle page change
  const handlePageChange = (event, value) => {
    setPage(value);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };
  
  // Handle sort changes
  const handleSortChange = (event) => {
    setFilters(prev => ({...prev, sortBy: event.target.value}));
  };
  
  // Toggle filter visibility
  const toggleFilters = () => {
    setShowFilters(!showFilters);
  };
  
  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 8 }}>
      <Box sx={{ mb: 5 }}>
        <Typography variant="h4" gutterBottom sx={{ 
          fontWeight: 'bold', 
          color: theme.palette.primary.main,
          display: 'flex',
          alignItems: 'center'
        }}>
          <DirectionsCar sx={{ mr: 1, fontSize: 32 }} />
          Car Marketplace
        </Typography>
        <Typography variant="subtitle1" color="text.secondary">
          Browse all available cars from our community. Filter, sort, and find your perfect match.
          {isAuthenticated && <span style={{ fontStyle: 'italic' }}> Your own listings are not shown here.</span>}
        </Typography>
      </Box>
      
      <Grid container spacing={3}>
        {/* Search & Sort Bar */}
        <Grid item xs={12}>
          <StyledFilterPaper>
            <Grid container spacing={2} alignItems="center">
              <Grid item xs={12} sm={6} md={4}>
                <TextField
                  fullWidth
                  placeholder="Search by make, model or title"
                  variant="outlined"
                  name="search"
                  value={filters.search}
                  onChange={handleFilterChange}
                  InputProps={{
                    startAdornment: <Search color="action" sx={{ mr: 1 }} />,
                  }}
                />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <FormControl fullWidth variant="outlined">
                  <InputLabel>Sort By</InputLabel>
                  <Select
                    value={filters.sortBy}
                    onChange={handleSortChange}
                    label="Sort By"
                    name="sortBy"
                    startAdornment={<Sort color="action" sx={{ mr: 1 }} />}
                  >
                    <MenuItem value="newest">Newest First</MenuItem>
                    <MenuItem value="oldest">Oldest First</MenuItem>
                    <MenuItem value="priceAsc">Price: Low to High</MenuItem>
                    <MenuItem value="priceDesc">Price: High to Low</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Button 
                  fullWidth 
                  variant="outlined" 
                  color="primary" 
                  startIcon={<FilterList />}
                  onClick={toggleFilters}
                  sx={{ height: '56px' }}
                >
                  {showFilters ? 'Hide Filters' : 'Show Filters'}
                </Button>
              </Grid>
              <Grid item xs={12} sm={6} md={2}>
                <Button 
                  fullWidth 
                  variant="outlined" 
                  color="secondary" 
                  startIcon={<Clear />}
                  onClick={handleResetFilters}
                  sx={{ height: '56px' }}
                >
                  Reset
                </Button>
              </Grid>
            </Grid>
          </StyledFilterPaper>
        </Grid>
        
        {/* Filters Section */}
        {showFilters && (
          <Grid item xs={12}>
            <StyledFilterPaper>
              <HeaderTypography variant="h6">
                Filter Options
              </HeaderTypography>
              
              <Grid container spacing={3}>
                {/* Make & Model */}
                <Grid item xs={12} sm={6} md={3}>
                  <FormControl fullWidth variant="outlined" sx={{ mb: 2 }}>
                    <InputLabel>Make</InputLabel>
                    <Select
                      name="make"
                      value={filters.make}
                      onChange={handleFilterChange}
                      label="Make"
                    >
                      <MenuItem value="">All Makes</MenuItem>
                      {Object.keys(carData).map((make) => (
                        <MenuItem key={make} value={make}>
                          {make}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  
                  <FormControl fullWidth variant="outlined" disabled={!filters.make}>
                    <InputLabel>Model</InputLabel>
                    <Select
                      name="model"
                      value={filters.model}
                      onChange={handleFilterChange}
                      label="Model"
                    >
                      <MenuItem value="">All Models</MenuItem>
                      {models.map((model) => (
                        <MenuItem key={model} value={model}>
                          {model}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>
                
                {/* Body Type & Condition */}
                <Grid item xs={12} sm={6} md={3}>
                  <FormControl fullWidth variant="outlined" sx={{ mb: 2 }}>
                    <InputLabel>Body Type</InputLabel>
                    <Select
                      name="bodyType"
                      value={filters.bodyType}
                      onChange={handleFilterChange}
                      label="Body Type"
                    >
                      <MenuItem value="">All Types</MenuItem>
                      {bodyTypeOptions.map((type) => (
                        <MenuItem key={type} value={type}>
                          {type}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  
                  <FormControl fullWidth variant="outlined">
                    <InputLabel>Condition</InputLabel>
                    <Select
                      name="condition"
                      value={filters.condition}
                      onChange={handleFilterChange}
                      label="Condition"
                    >
                      <MenuItem value="">All Conditions</MenuItem>
                      {conditionOptions.map((condition) => (
                        <MenuItem key={condition} value={condition}>
                          {condition}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>
                
                {/* Price Range */}
                <Grid item xs={12} sm={6} md={3}>
                  <Typography variant="subtitle2" gutterBottom>
                    Price Range (EGP)
                  </Typography>
                  
                  <Slider
                    value={priceRange}
                    onChange={handlePriceRangeChange}
                    valueLabelDisplay="auto"
                    min={0}
                    max={5000000}
                    step={10000}
                    sx={{ mt: 3, mb: 1 }}
                  />
                  
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 1 }}>
                    <Typography variant="body2">
                      {priceRange[0].toLocaleString()} EGP
                    </Typography>
                    <Typography variant="body2">
                      {priceRange[1].toLocaleString()} EGP
                    </Typography>
                  </Box>
                </Grid>
                
                {/* Year, Location, Fuel, Transmission */}
                <Grid item xs={12} sm={6} md={3}>
                  <Grid container spacing={2}>
                    <Grid item xs={6}>
                      <FormControl fullWidth variant="outlined" size="small">
                        <InputLabel>Min Year</InputLabel>
                        <Select
                          name="minYear"
                          value={filters.minYear}
                          onChange={handleFilterChange}
                          label="Min Year"
                        >
                          {Array.from({ length: new Date().getFullYear() - 1999 }, (_, i) => (
                            <MenuItem key={2000 + i} value={2000 + i}>
                              {2000 + i}
                            </MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                    </Grid>
                    <Grid item xs={6}>
                      <FormControl fullWidth variant="outlined" size="small">
                        <InputLabel>Max Year</InputLabel>
                        <Select
                          name="maxYear"
                          value={filters.maxYear}
                          onChange={handleFilterChange}
                          label="Max Year"
                        >
                          {Array.from({ length: new Date().getFullYear() - 1999 }, (_, i) => (
                            <MenuItem key={2000 + i} value={2000 + i}>
                              {2000 + i}
                            </MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                    </Grid>
                  </Grid>
                  
                  <FormControl fullWidth variant="outlined" sx={{ mt: 2 }}>
                    <InputLabel>Location</InputLabel>
                    <Select
                      name="location"
                      value={filters.location}
                      onChange={handleFilterChange}
                      label="Location"
                    >
                      <MenuItem value="">All Locations</MenuItem>
                      {locationOptions.map((location) => (
                        <MenuItem key={location} value={location}>
                          {location}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  
                  <Grid container spacing={2} sx={{ mt: 0.5 }}>
                    <Grid item xs={6}>
                      <FormControl fullWidth variant="outlined" size="small">
                        <InputLabel>Fuel Type</InputLabel>
                        <Select
                          name="fuelType"
                          value={filters.fuelType}
                          onChange={handleFilterChange}
                          label="Fuel Type"
                        >
                          <MenuItem value="">All</MenuItem>
                          {fuelTypeOptions.map((type) => (
                            <MenuItem key={type} value={type}>
                              {type}
                            </MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                    </Grid>
                    <Grid item xs={6}>
                      <FormControl fullWidth variant="outlined" size="small">
                        <InputLabel>Transmission</InputLabel>
                        <Select
                          name="transmissionType"
                          value={filters.transmissionType}
                          onChange={handleFilterChange}
                          label="Transmission"
                        >
                          <MenuItem value="">All</MenuItem>
                          {transmissionOptions.map((type) => (
                            <MenuItem key={type} value={type}>
                              {type.charAt(0).toUpperCase() + type.slice(1)}
                            </MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                    </Grid>
                  </Grid>
                </Grid>
                
                {/* Color Multi-select */}
                <Grid item xs={12}>
                  <FormControl fullWidth variant="outlined">
                    <InputLabel>Colors</InputLabel>
                    <Select
                      multiple
                      name="color"
                      value={filters.color}
                      onChange={handleColorChange}
                      input={<OutlinedInput label="Colors" />}
                      renderValue={(selected) => (
                        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                          {selected.map((value) => (
                            <Chip key={value} label={value} size="small" />
                          ))}
                        </Box>
                      )}
                    >
                      {colorOptions.map((color) => (
                        <MenuItem key={color} value={color}>
                          <Checkbox checked={filters.color.indexOf(color) > -1} />
                          <ListItemText primary={color} />
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>
              </Grid>
            </StyledFilterPaper>
          </Grid>
        )}
        
        {/* Loading indicator */}
        {loading && (
          <Grid item xs={12} sx={{ display: 'flex', justifyContent: 'center', my: 5 }}>
            <CircularProgress />
          </Grid>
        )}
        
        {/* Error message */}
        {error && (
          <Grid item xs={12}>
            <Paper sx={{ p: 3, textAlign: 'center', bgcolor: alpha(theme.palette.error.main, 0.1) }}>
              <Typography color="error">{error}</Typography>
              <Button 
                variant="outlined" 
                color="primary" 
                sx={{ mt: 2 }}
                onClick={() => {
                  setError(null);
                  setPage(1);
                  handleResetFilters();
                }}
              >
                Try Again
              </Button>
            </Paper>
          </Grid>
        )}
        
        {/* No results message */}
        {!loading && !error && listings.length === 0 && (
          <Grid item xs={12}>
            <Paper sx={{ p: 4, textAlign: 'center', my: 3 }}>
              <Typography variant="h6" color="text.secondary" sx={{ mb: 2 }}>
                No cars found matching your criteria
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                Try adjusting your filters or searching for something else
              </Typography>
              <Button 
                variant="contained" 
                color="primary" 
                onClick={handleResetFilters}
                startIcon={<Clear />}
              >
                Clear Filters
              </Button>
            </Paper>
          </Grid>
        )}
        
        {/* Car listings */}
        {!loading && !error && listings.length > 0 && (
          <>
            <Grid item xs={12}>
              <Typography variant="subtitle1" sx={{ mb: 2, mt: 1, fontWeight: 500 }}>
                Showing {listings.length} cars {filters.make ? `(${filters.make}${filters.model ? ` ${filters.model}` : ''})` : ''} 
                {totalPages > 1 && ` - Page ${page} of ${totalPages}`}
              </Typography>
              <Divider sx={{ mb: 3 }} />
            </Grid>
            
            <Grid container spacing={3}>
              {listings.map((listing) => (
                <Grid item xs={12} sm={6} md={4} lg={3} key={listing._id}>
                  <ListingCard>
                    <CardActionArea onClick={() => handleViewListing(listing._id)}>
                      <CardMedia
                        component="img"
                        height="200"
                        image={listing.images && listing.images.length > 0 ? `${process.env.REACT_APP_API_URL || 'http://localhost:8000'}/uploads/${listing.images[0]}` : '/default-car.jpg'}
                        alt={listing.title}
                        sx={{ objectFit: 'cover' }}
                      />
                      <CardContent sx={{ flexGrow: 1, pb: 1 }}>
                        <Typography gutterBottom variant="h6" component="div" noWrap sx={{ fontWeight: 'bold' }}>
                          {listing.title}
                        </Typography>
                        
                        <Typography variant="h6" color="primary" sx={{ fontWeight: 'bold', mb: 1 }}>
                          {Number(listing.price).toLocaleString()} EGP
                        </Typography>
                        
                        <Box sx={{ mb: 1.5 }}>
                          <Typography variant="body2" color="text.secondary" sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
                            <Person sx={{ fontSize: 16, mr: 0.5 }} />
                            {listing.owner_name ? listing.owner_name : "Listed by Seller"}
                          </Typography>
                          
                          <Typography variant="body2" color="text.secondary" sx={{ display: 'flex', alignItems: 'center' }}>
                            <LocationOn sx={{ fontSize: 16, mr: 0.5 }} />
                            {listing.location}
                          </Typography>
                        </Box>
                        
                        <Box sx={{ display: 'flex', flexWrap: 'wrap', mt: 1 }}>
                          <ListingInfoChip 
                            size="small" 
                            icon={<CalendarToday />} 
                            label={listing.year} 
                            color={theme.palette.info.main} 
                          />
                          <ListingInfoChip 
                            size="small" 
                            icon={<Speed />} 
                            label={`${Number(listing.kilometers).toLocaleString()} km`} 
                            color={theme.palette.warning.main} 
                          />
                          <ListingInfoChip 
                            size="small" 
                            icon={<Settings />} 
                            label={listing.transmissionType === 'automatic' ? 'Auto' : 'Manual'} 
                            color={theme.palette.success.main} 
                          />
                          <ListingInfoChip 
                            size="small" 
                            icon={<Phone />} 
                            label={listing.showPhoneNumber ? "Phone Available" : "Contact via Chat"} 
                            color={theme.palette.secondary.main} 
                          />
                        </Box>
                      </CardContent>
                    </CardActionArea>
                  </ListingCard>
                </Grid>
              ))}
            </Grid>
            
            {/* Pagination */}
            {totalPages > 1 && (
              <Grid item xs={12} sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}>
                <Stack spacing={2}>
                  <Pagination 
                    count={totalPages} 
                    page={page} 
                    onChange={handlePageChange} 
                    color="primary"
                    size="large"
                    showFirstButton
                    showLastButton
                  />
                </Stack>
              </Grid>
            )}
          </>
        )}
      </Grid>
    </Container>
  );
};

export default CarMarketplace;